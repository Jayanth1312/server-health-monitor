"""
SHM — modern, lightweight curses TUI for the Server Health Monitor.

Single-file, stdlib + psutil only. No heavy frameworks.

Views (1-6 / Tab):
    1 Overview   2 Processes   3 Disk   4 Network   5 Alerts   6 Config

Distinctive touches:
    * Sub-character resolution bars (▏▎▍▌▋▊▉█)
    * Live sparklines for CPU / MEM / NET (▁▂▃▄▅▆▇█)
    * Heartbeat pulse synced to collector cadence
    * In-TUI config editor with dirty-state tracking + atomic save
    * Searchable / sortable process table with safe SIGTERM
    * Toast notifications when fresh alerts fire
"""

from __future__ import annotations

import curses
import json
import os
import signal
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Deque, Dict, List, Optional, Tuple

import psutil

from monitor.config import MonitorConfig

# ── tunables ───────────────────────────────────────────────────────────────
_REFRESH      = 2.0    # seconds between full metric snapshots
_NET_SAMPLE   = 1.0    # seconds between net rate samples
_POLL_MS      = 50     # main loop poll interval
_HISTORY      = 240    # samples kept per metric (~ 8 min @ 2s)
_TOAST_TTL    = 4.0    # seconds a toast stays visible

# ── colour pair ids ────────────────────────────────────────────────────────
C_OK     = 1   # green
C_WARN   = 2   # yellow
C_CRIT   = 3   # red
C_INFO   = 4   # cyan
C_TEXT   = 5   # white
C_TITLE  = 6   # bright white / accent
C_DIM    = 7   # subtle gray
C_ACCENT = 8   # magenta — selection / branding
C_TAB_ON = 9   # active tab fg
C_TAB_OFF= 10  # inactive tab fg
C_BAR_BG = 11  # bar trough
C_HEART  = 12  # heartbeat
C_BADGE  = 13  # alert badge
C_STATUS = 14  # status bar (header/footer)

# ── views ─────────────────────────────────────────────────────────────────
VIEWS = ("Overview", "Processes", "Disk", "Network", "Alerts", "Config")
V_OVERVIEW, V_PROCS, V_DISK, V_NET, V_ALERTS, V_CONFIG = range(6)

# ── unicode kits ──────────────────────────────────────────────────────────
_BAR_SUBS  = " ▏▎▍▌▋▊▉█"
_SPARKS    = " ▁▂▃▄▅▆▇█"
_HEARTBEAT = "●○"


# ══════════════════════════════════════════════════════════════════════════
# helpers
# ══════════════════════════════════════════════════════════════════════════

def _fmt_bytes(n: float) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if abs(n) < 1024:
            return f"{n:5.1f}{unit}"
        n /= 1024
    return f"{n:5.1f}P"


def _fmt_rate(bps: float) -> str:
    return _fmt_bytes(bps) + "/s"


def _fmt_uptime(secs: float) -> str:
    td = timedelta(seconds=int(secs))
    h, r = divmod(td.seconds, 3600)
    m, s = divmod(r, 60)
    return f"{td.days}d {h:02d}:{m:02d}:{s:02d}" if td.days else f"{h:02d}:{m:02d}:{s:02d}"


def _hbar(pct: float, width: int) -> str:
    """Smooth horizontal bar with 1/8-cell sub-resolution."""
    pct = max(0.0, min(100.0, pct))
    cells = pct / 100 * width
    full  = int(cells)
    sub   = round((cells - full) * 8)
    if sub == 8:
        full += 1
        sub = 0
    out = "█" * full
    if full < width:
        out += _BAR_SUBS[sub]
        out += " " * (width - full - 1)
    return out


def _sparkline(values: List[float], width: int, lo: Optional[float] = None,
               hi: Optional[float] = None) -> str:
    if not values:
        return " " * width
    sample = values[-width:]
    pad    = width - len(sample)
    mn = lo if lo is not None else min(sample)
    mx = hi if hi is not None else max(sample)
    if mx <= mn:
        mx = mn + 1.0
    out = " " * pad
    for v in sample:
        idx = round((v - mn) / (mx - mn) * 8)
        out += _SPARKS[max(0, min(8, idx))]
    return out


# ── braille sparkline ───────────────────────────────────────────────────────
#
# Braille cells pack a 2-column × 4-row dot matrix into one character at
# U+2800 + dots. That gives 2× the horizontal resolution and ~4 y-levels per
# cell compared to the block sparkline above — much smoother for live charts.
#
# Dot layout (bits relative to U+2800):
#   col 0    col 1
#   0x01 ·   · 0x08
#   0x02 ·   · 0x10
#   0x04 ·   · 0x20
#   0x40 ·   · 0x80

_BRAILLE_BITS = (
    (0x01, 0x02, 0x04, 0x40),  # left column, top→bottom
    (0x08, 0x10, 0x20, 0x80),  # right column, top→bottom
)


def _braille_fill(col: int, level: int) -> int:
    """Bottom-up fill: level 0→no dots, level 4→all four dots in column."""
    bits = 0
    for i in range(max(0, min(4, level))):
        bits |= _BRAILLE_BITS[col][3 - i]
    return bits


def _chart(values: List[float], width: int,
                   lo: Optional[float] = None, hi: Optional[float] = None) -> str:
    """Single-row braille sparkline — 2 samples / cell, 5 y-levels."""
    if not values or width <= 0:
        return " " * max(0, width)
    sample = list(values)[-(width * 2):]
    pad = (width * 2) - len(sample)
    sample = [0.0] * pad + sample

    mn = lo if lo is not None else min(sample)
    mx = hi if hi is not None else max(sample)
    if mx <= mn:
        mx = mn + 1.0

    out = []
    for i in range(width):
        left  = sample[i * 2]
        right = sample[i * 2 + 1] if i * 2 + 1 < len(sample) else left
        ll = round((left  - mn) / (mx - mn) * 4)
        rl = round((right - mn) / (mx - mn) * 4)
        out.append(chr(0x2800 + _braille_fill(0, ll) + _braille_fill(1, rl)))
    return "".join(out)


# Braille glyphs aren't in every terminal font and render as tofu when
# missing. Block sparklines are the safe default; set SHM_BRAILLE=1 to
# opt into the higher-resolution braille charts.
_USE_BRAILLE = os.environ.get("SHM_BRAILLE", "").strip().lower() in ("1", "true", "yes", "on")


def _chart(values: List[float], width: int,
           lo: Optional[float] = None, hi: Optional[float] = None) -> str:
    """Dispatch to block or braille sparkline based on SHM_BRAILLE."""
    if _USE_BRAILLE:
        return _chart(values, width, lo, hi)
    return _sparkline(values, width, lo, hi)


def _severity_pair(pct: float, warn: float, crit: float) -> int:
    if pct >= crit:
        return C_CRIT
    if pct >= warn:
        return C_WARN
    return C_OK


def _put(win, y: int, x: int, text: str, attr: int = 0) -> None:
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x >= w or x < 0:
        return
    try:
        win.addstr(y, x, text[: max(0, w - x - 1)], attr)
    except curses.error:
        pass


def _hline(win, y: int, x: int, width: int, ch: str = "─", attr: int = 0) -> None:
    _put(win, y, x, ch * width, attr)


def _panel(win, y: int, x: int, h: int, w: int, title: str,
           title_color: int = None,
           meta: str = "") -> Tuple[int, int, int, int]:
    """Draw a rounded panel with title + optional right-aligned meta.

    Returns (inner_y, inner_x, inner_h, inner_w)."""
    if w < 6 or h < 3:
        return (y + 1, x + 1, max(0, h - 2), max(0, w - 2))
    dim = curses.color_pair(C_DIM)
    title_attr = curses.color_pair(title_color) | curses.A_BOLD \
                 if title_color else curses.color_pair(C_TITLE) | curses.A_BOLD

    _put(win, y, x, "╭─", dim)
    _put(win, y, x + 2, f" {title} ", title_attr)
    used = 2 + 2 + len(title)
    right_pad = 1
    if meta:
        meta_text = f" {meta} "
        meta_attr = curses.color_pair(C_DIM)
        meta_start = x + w - 1 - len(meta_text) - 1
        fill = meta_start - (x + used)
        if fill > 0:
            _put(win, y, x + used, "─" * fill, dim)
        _put(win, y, meta_start, meta_text, meta_attr)
        _put(win, y, x + w - 2, "─", dim)
    else:
        fill = (x + w - 1) - (x + used)
        if fill > 0:
            _put(win, y, x + used, "─" * fill, dim)
    _put(win, y, x + w - 1, "╮", dim)

    for i in range(1, h - 1):
        _put(win, y + i, x,         "│", dim)
        _put(win, y + i, x + w - 1, "│", dim)

    _put(win, y + h - 1, x, "╰" + "─" * (w - 2) + "╯", dim)
    return (y + 1, x + 2, h - 2, w - 4)


# ══════════════════════════════════════════════════════════════════════════
# data layer
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class History:
    cpu:  Deque[float] = field(default_factory=lambda: deque(maxlen=_HISTORY))
    mem:  Deque[float] = field(default_factory=lambda: deque(maxlen=_HISTORY))
    swap: Deque[float] = field(default_factory=lambda: deque(maxlen=_HISTORY))
    rx:   Deque[float] = field(default_factory=lambda: deque(maxlen=_HISTORY))
    tx:   Deque[float] = field(default_factory=lambda: deque(maxlen=_HISTORY))


class Collector:
    """Background sampler. Lock-protected snapshot + history rings."""

    def __init__(self) -> None:
        self.hostname = socket.gethostname()
        self._lock    = threading.Lock()
        self._data: dict = {}
        self.history = History()
        self.ready   = threading.Event()
        self.tick    = 0

        # prime psutil per-process cpu_percent
        psutil.cpu_percent(interval=None)
        for p in psutil.process_iter(["cpu_percent"]):
            try: p.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass

        self._last_net  = psutil.net_io_counters()
        self._last_time = time.monotonic()

    def _snapshot(self) -> dict:
        cpu_pct  = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(interval=None, percpu=True)

        try:
            load = os.getloadavg()
        except (AttributeError, OSError):
            load = (0.0, 0.0, 0.0)

        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()

        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "mp": part.mountpoint, "fs": part.fstype,
                    "device": part.device,
                    "used": u.used, "total": u.total,
                    "free": u.free, "pct": u.percent,
                })
            except (PermissionError, OSError):
                pass

        net = psutil.net_io_counters()
        now = time.monotonic()
        dt  = max(now - self._last_time, 1e-3)
        rx_rate = (net.bytes_recv - self._last_net.bytes_recv) / dt
        tx_rate = (net.bytes_sent - self._last_net.bytes_sent) / dt
        self._last_net, self._last_time = net, now

        ifaces = []
        try:
            per_if = psutil.net_io_counters(pernic=True)
            for name, c in per_if.items():
                ifaces.append({
                    "name": name,
                    "rx": c.bytes_recv, "tx": c.bytes_sent,
                    "rx_pkts": c.packets_recv, "tx_pkts": c.packets_sent,
                    "errs": c.errin + c.errout, "drop": c.dropin + c.dropout,
                })
        except Exception:
            pass

        procs = []
        for p in psutil.process_iter(
                ["pid", "name", "username", "cpu_percent", "memory_percent", "status"]):
            try:
                procs.append({
                    "pid":  p.info["pid"],
                    "name": p.info["name"] or "?",
                    "user": (p.info["username"] or "")[:10],
                    "cpu":  p.cpu_percent(interval=None),
                    "mem":  p.info["memory_percent"] or 0.0,
                    "stat": p.info["status"] or "",
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        return {
            "cpu": cpu_pct, "cores": per_core, "load": load,
            "mem": mem, "swap": swap,
            "disks": disks,
            "net_tx": net.bytes_sent, "net_rx": net.bytes_recv,
            "tx_rate": tx_rate, "rx_rate": rx_rate,
            "ifaces": ifaces,
            "procs": procs,
            "uptime": time.time() - psutil.boot_time(),
            "ts": time.time(),
        }

    def run(self, stop: threading.Event) -> None:
        time.sleep(0.4)
        while not stop.is_set():
            try:
                data = self._snapshot()
                with self._lock:
                    self._data = data
                    self.history.cpu.append(data["cpu"])
                    self.history.mem.append(data["mem"].percent)
                    self.history.swap.append(data["swap"].percent)
                    self.history.rx.append(data["rx_rate"])
                    self.history.tx.append(data["tx_rate"])
                    self.tick += 1
                self.ready.set()
            except Exception:
                pass
            stop.wait(_REFRESH)

    @property
    def data(self) -> dict:
        with self._lock:
            return dict(self._data)


# ══════════════════════════════════════════════════════════════════════════
# alerts tail reader
# ══════════════════════════════════════════════════════════════════════════

class AlertTail:
    def __init__(self, path: str) -> None:
        self.path  = Path(path)
        self.items: List[dict] = []
        self.last_mtime = 0.0
        self.fresh_count = 0   # alerts arrived since last view of Alerts tab

    def refresh(self, max_items: int = 200) -> bool:
        """Reload if file changed. Returns True if new items appeared."""
        try:
            if not self.path.exists():
                return False
            m = self.path.stat().st_mtime
            if m == self.last_mtime:
                return False
            prev = len(self.items)
            with open(self.path, "r") as fh:
                lines = fh.readlines()[-max_items:]
            self.items = []
            for line in lines:
                try:
                    self.items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            self.last_mtime = m
            new = max(0, len(self.items) - prev)
            self.fresh_count += new
            return new > 0
        except Exception:
            return False


# ══════════════════════════════════════════════════════════════════════════
# UI state
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Toast:
    text:    str
    pair:    int
    expires: float


@dataclass
class UIState:
    view:        int  = V_OVERVIEW
    proc_idx:    int  = 0
    proc_sort:   str  = "cpu"   # cpu | mem | pid | name
    proc_filter: str  = ""
    proc_filter_active: bool = False
    proc_scroll: int  = 0

    cfg_idx:     int  = 0
    cfg_dirty:   bool = False
    cfg_editing: bool = False
    cfg_buffer:  str  = ""
    cfg_msg:     str  = ""
    cfg_fresh:   bool = False   # first printable key replaces pre-filled buffer

    alert_idx:   int  = 0
    alert_scroll:int  = 0

    show_help:   bool = False
    toasts:      List[Toast] = field(default_factory=list)
    confirm:     Optional[Tuple[str, Callable[[], None]]] = None
    footer_info: str = ""

    def push_toast(self, text: str, pair: int = C_INFO) -> None:
        self.toasts.append(Toast(text, pair, time.monotonic() + _TOAST_TTL))
        self.toasts = self.toasts[-3:]

    def prune_toasts(self) -> None:
        now = time.monotonic()
        self.toasts = [t for t in self.toasts if t.expires > now]


# ── flat config field list (label, dotted path, type) ─────────────────────
CONFIG_FIELDS: List[Tuple[str, str, str, str]] = [
    # section, label, path, type
    ("Thresholds", "CPU %",                "thresholds.cpu_percent",     "float"),
    ("Thresholds", "Memory %",             "thresholds.memory_percent",  "float"),
    ("Thresholds", "Disk %",               "thresholds.disk_percent",    "float"),
    ("Thresholds", "Swap %",               "thresholds.swap_percent",    "float"),

    ("Alerts",     "Enabled",              "alerts.enabled",             "bool"),
    ("Alerts",     "Cooldown (min)",       "alerts.cooldown_minutes",    "int"),
    ("Alerts",     "Log file",             "alerts.log_file",            "str"),

    ("SMTP",       "Enabled",              "smtp.enabled",               "bool"),
    ("SMTP",       "Host",                 "smtp.host",                  "str"),
    ("SMTP",       "Port",                 "smtp.port",                  "int"),
    ("SMTP",       "Username",             "smtp.username",              "str"),
    ("SMTP",       "Password",             "smtp.password",              "secret"),
    ("SMTP",       "From",                 "smtp.from_addr",             "str"),
    ("SMTP",       "To (comma sep)",       "smtp.to_addrs",              "list"),
    ("SMTP",       "Use TLS",              "smtp.use_tls",               "bool"),

    ("General",    "Collection interval (s)", "collection_interval",     "int"),
    ("General",    "Metrics log",          "metrics_log",                "str"),
]


def _cfg_get(cfg: MonitorConfig, path: str):
    obj = cfg
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def _cfg_set(cfg: MonitorConfig, path: str, value: str, kind: str) -> None:
    parts = path.split(".")
    obj = cfg
    for part in parts[:-1]:
        obj = getattr(obj, part)
    field_name = parts[-1]

    if kind == "bool":
        v = value.strip().lower() in ("1", "true", "yes", "on", "y")
    elif kind == "int":
        v = int(value)
    elif kind == "float":
        v = float(value)
    elif kind == "list":
        v = [s.strip() for s in value.split(",") if s.strip()]
    else:
        v = value

    setattr(obj, field_name, v)


def _cfg_display(value, kind: str) -> str:
    if kind == "secret":
        return "••••••••" if value else "(unset)"
    if kind == "bool":
        return "● on" if value else "○ off"
    if kind == "list":
        return ", ".join(value) if value else "(empty)"
    return str(value) if value != "" else "(empty)"


# ══════════════════════════════════════════════════════════════════════════
# rendering
# ══════════════════════════════════════════════════════════════════════════

def _init_colors() -> None:
    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        # Some terminals (notably Windows conhost via windows-curses) don't
        # support default colors. Fall back to pair 0 (terminal default).
        pass
    pairs = {
        C_OK:      (curses.COLOR_GREEN,    -1),
        C_WARN:    (curses.COLOR_YELLOW,   -1),
        C_CRIT:    (curses.COLOR_RED,      -1),
        C_INFO:    (curses.COLOR_CYAN,     -1),
        C_TEXT:    (curses.COLOR_WHITE,    -1),
        C_TITLE:   (15,                    -1),
        C_DIM:     (8,                     -1),
        C_ACCENT:  (curses.COLOR_MAGENTA,  -1),
        # active tab: bright fg on magenta — high contrast
        C_TAB_ON:  (15,                    curses.COLOR_MAGENTA),
        # inactive tabs: normal white — readable on any background
        C_TAB_OFF: (curses.COLOR_WHITE,    -1),
        C_BAR_BG:  (236,                   -1),
        C_HEART:   (curses.COLOR_RED,      -1),
        C_BADGE:   (curses.COLOR_BLACK,    curses.COLOR_RED),
        C_STATUS:  (curses.COLOR_WHITE,    -1),  # transparent background
    }
    for pid, (fg, bg) in pairs.items():
        try:
            curses.init_pair(pid, fg, bg)
        except curses.error:
            curses.init_pair(pid, 7, -1)


def _draw_topbar(win, col: Collector, alerts: AlertTail, ui: UIState) -> None:
    h, w = win.getmaxyx()
    d = col.data
    ts = datetime.now().strftime("%H:%M:%S")
    uptime = _fmt_uptime(d.get("uptime", 0)) if d else "—"

    beat = _HEARTBEAT[col.tick % 2]
    left = f" {beat} SHM "
    mid  = f" {col.hostname} • up {uptime} • {ts} "

    _put(win, 0, 0, left,
         curses.color_pair(C_TAB_ON) | curses.A_BOLD)
    _put(win, 0, len(left), mid,
         curses.color_pair(C_STATUS))

    # right side: alert badge + cpu glance
    right_chunks = []
    cpu = d.get("cpu", 0.0)
    cp = _severity_pair(cpu, 70, 90)
    right_chunks.append((f" CPU {cpu:4.1f}% ", curses.color_pair(cp) | curses.A_BOLD))

    if alerts.items:
        sev_critical = sum(1 for a in alerts.items if a.get("severity") == "critical")
        badge = f" ⚠ {len(alerts.items)} "
        # Use C_BADGE (red bg) for critical, C_WARN (yellow fg) for others
        attr = curses.color_pair(C_BADGE) | curses.A_BOLD if sev_critical else curses.color_pair(C_WARN) | curses.A_BOLD
        right_chunks.append((badge, attr))

    # paint right-to-left
    x = w - 2
    for text, attr in reversed(right_chunks):
        x -= len(text)
        if x > len(left) + len(mid):
            _put(win, 0, x, text, attr)


def _draw_tabs(win, ui: UIState, alerts: AlertTail) -> None:
    h, w = win.getmaxyx()
    y = 1

    # remember where each tab ends so we can underline only the active chip
    segments: List[Tuple[int, int, bool]] = []  # (start_x, end_x, is_active)
    x = 1
    for i, name in enumerate(VIEWS):
        label = name
        if i == V_ALERTS and alerts.items:
            label = f"{name} ({len(alerts.items)})"

        active = (i == ui.view)
        if active:
            chip = f" ▸ {i+1} {label} "
            attr = curses.color_pair(C_TAB_ON) | curses.A_BOLD
        else:
            num_attr  = curses.color_pair(C_ACCENT) | curses.A_BOLD
            text_attr = curses.color_pair(C_TEXT)
            # paint manually to keep the digit prefix colored differently
            if x + 6 + len(label) >= w - 2:
                break
            _put(win, y, x,     " ",                  text_attr)
            _put(win, y, x + 1, f"{i+1}",             num_attr)
            _put(win, y, x + 2, f" {label} ",         text_attr)
            seg_len = 3 + len(label) + 1
            segments.append((x, x + seg_len, False))
            x += seg_len + 1
            continue

        if x + len(chip) >= w - 2:
            break
        _put(win, y, x, chip, attr)
        segments.append((x, x + len(chip), active))
        x += len(chip) + 1

    # underline divider; thicker under the active chip
    for sx in range(0, w - 1):
        ch = "─"
        attr = curses.color_pair(C_DIM)
        for (s, e, active) in segments:
            if active and s <= sx < e:
                ch = "━"
                attr = curses.color_pair(C_ACCENT) | curses.A_BOLD
                break
        _put(win, 2, sx, ch, attr)


def _draw_footer(win, ui: UIState) -> None:
    h, w = win.getmaxyx()
    if ui.cfg_editing:
        keys = "  ↵ commit   esc cancel "
    elif ui.confirm:
        keys = f"  {ui.confirm[0]}   y confirm   n cancel "
    elif ui.show_help:
        keys = "  ? close help "
    else:
        common = " 1-6/⇥ tabs   ? help   q quit "
        per = {
            V_OVERVIEW: " ",
            V_PROCS:    " ↑↓ select   / search   s sort   k kill ",
            V_DISK:     " ",
            V_NET:      " ",
            V_ALERTS:   " ↑↓ scroll ",
            V_CONFIG:   " ↑↓ select   ↵ edit   s save ",
        }.get(ui.view, " ")
        keys = per + "│" + common
    # Draw a thin separator above the footer to provide "seperation" while blending
    # If there's extra info from the view, bake it into the line
    sep = "─" * w
    if ui.footer_info:
        info = f" {ui.footer_info} "
        if len(info) < w - 10:
            sep = "──" + info + "─" * (w - 2 - len(info))
    
    _put(win, h - 2, 0, sep[:w-1], curses.color_pair(C_DIM))
    _put(win, h - 1, 0, keys.ljust(w - 1)[: w - 1],
         curses.color_pair(C_TEXT))


def _draw_toasts(win, ui: UIState) -> None:
    h, w = win.getmaxyx()
    ui.prune_toasts()
    for i, t in enumerate(ui.toasts[-3:]):
        text = f"  ▌ {t.text}  "
        x = max(2, w - len(text) - 2)
        y = 3 + i
        _put(win, y, x, text,
             curses.color_pair(t.pair) | curses.A_BOLD | curses.A_REVERSE)


# ── view: overview ────────────────────────────────────────────────────────

def _fill_cpu_panel(win, col: Collector, y: int, x: int, h: int, w: int) -> None:
    d = col.data
    cpu = d["cpu"]
    cp = _severity_pair(cpu, 70, 90)
    cores = d["cores"]
    n = psutil.cpu_count(logical=True) or len(cores)
    load = d["load"]

    # row 0: main value + load avg + thread count
    _put(win, y, x, f"{cpu:5.1f}%", curses.color_pair(cp) | curses.A_BOLD)
    _put(win, y, x + 8, f"load {load[0]:.2f} {load[1]:.2f} {load[2]:.2f}",
         curses.color_pair(C_DIM))
    tail = f"{n:>2} threads"
    _put(win, y, x + max(8, w - len(tail)), tail, curses.color_pair(C_DIM))

    # row 1: smooth bar
    if h >= 2:
        _put(win, y + 1, x, _hbar(cpu, w), curses.color_pair(cp) | curses.A_BOLD)

    # row 2: braille sparkline — 2 samples per cell, longer history visible
    if h >= 3:
        _put(win, y + 2, x, _chart(list(col.history.cpu), w, 0, 100),
             curses.color_pair(C_INFO))

    # row 3: per-core strip
    if h >= 4 and cores:
        seg_w = max(6, w // max(len(cores), 1))
        xi = x
        for i, v in enumerate(cores):
            if xi + seg_w > x + w:
                break
            if v >= 90:   ch, p = "█", C_CRIT
            elif v >= 70: ch, p = "▆", C_WARN
            elif v >= 30: ch, p = "▃", C_OK
            else:         ch, p = "▁", C_DIM
            _put(win, y + 3, xi, f"c{i} {ch}{v:3.0f}"[:seg_w], curses.color_pair(p))
            xi += seg_w

    # row 4: temperatures (if available)
    if h >= 5:
        try:
            temps = psutil.sensors_temperatures()
        except (AttributeError, OSError):
            temps = {}
        if temps:
            for label, arr in temps.items():
                if not arr: continue
                avg = sum(t.current for t in arr) / len(arr)
                mx  = max(t.current for t in arr)
                tp = C_CRIT if mx >= 85 else C_WARN if mx >= 70 else C_OK
                _put(win, y + 4, x,
                     f"temp {label[:12]}: avg {avg:.0f}°C  max {mx:.0f}°C",
                     curses.color_pair(tp))
                break
        else:
            # show uptime instead on systems without sensors
            _put(win, y + 4, x,
                 f"uptime {_fmt_uptime(d.get('uptime', 0))}",
                 curses.color_pair(C_DIM))


def _fill_mem_panel(win, col: Collector, y: int, x: int, h: int, w: int) -> None:
    d = col.data
    mem  = d["mem"]
    swap = d["swap"]
    mp = _severity_pair(mem.percent, 70, 85)

    _put(win, y, x, f"{mem.percent:5.1f}%", curses.color_pair(mp) | curses.A_BOLD)
    _put(win, y, x + 8,
         f"{mem.used/1024**3:.1f} / {mem.total/1024**3:.1f} GB",
         curses.color_pair(C_TEXT))
    _put(win, y, x + w - 16, f"avail {mem.available/1024**3:4.1f} GB",
         curses.color_pair(C_DIM))

    if h >= 2:
        _put(win, y + 1, x, _hbar(mem.percent, w), curses.color_pair(mp) | curses.A_BOLD)

    if h >= 3:
        spark = _chart(list(col.history.mem), w, 0, 100)
        _put(win, y + 2, x, spark, curses.color_pair(C_INFO))

    if h >= 4:
        if swap.total:
            sp = _severity_pair(swap.percent, 50, 80)
            _put(win, y + 3, x, "swap ", curses.color_pair(C_DIM))
            sb_w = max(6, w - 28)
            _put(win, y + 3, x + 5, _hbar(swap.percent, sb_w),
                 curses.color_pair(sp))
            _put(win, y + 3, x + 5 + sb_w + 1,
                 f" {swap.used/1024**3:.1f}/{swap.total/1024**3:.1f}G {swap.percent:4.1f}%",
                 curses.color_pair(sp))
        else:
            _put(win, y + 3, x, "swap disabled", curses.color_pair(C_DIM))

    if h >= 5:
        cached = getattr(mem, "cached", 0)
        buffers = getattr(mem, "buffers", 0)
        _put(win, y + 4, x,
             f"cached {cached/1024**3:4.1f}G   buffers {buffers/1024**3:4.1f}G",
             curses.color_pair(C_DIM))


def _fill_net_panel(win, col: Collector, y: int, x: int, h: int, w: int) -> None:
    d = col.data
    rx = d["rx_rate"]; tx = d["tx_rate"]
    rx_max = max(list(col.history.rx) or [1.0])
    tx_max = max(list(col.history.tx) or [1.0])

    # sparklines prefixed with a small arrow — braille for smoother curves
    _put(win, y,     x,     "↓ ", curses.color_pair(C_OK) | curses.A_BOLD)
    _put(win, y,     x + 2, _chart(list(col.history.rx), w - 2, 0, max(rx_max, 1)),
         curses.color_pair(C_OK))
    if h >= 2:
        _put(win, y + 1, x,     "↑ ", curses.color_pair(C_ACCENT) | curses.A_BOLD)
        _put(win, y + 1, x + 2, _chart(list(col.history.tx), w - 2, 0, max(tx_max, 1)),
             curses.color_pair(C_ACCENT))
    if h >= 3:
        _put(win, y + 2, x,
             f"total ↓ {_fmt_bytes(d['net_rx'])}   ↑ {_fmt_bytes(d['net_tx'])}",
             curses.color_pair(C_DIM))
    if h >= 4:
        _put(win, y + 3, x,
             f"peak  ↓ {_fmt_rate(rx_max)}   ↑ {_fmt_rate(tx_max)}",
             curses.color_pair(C_DIM))
    if h >= 5:
        nic_names = ", ".join(n["name"] for n in d.get("ifaces", [])[:5])
        if nic_names:
            _put(win, y + 4, x, f"ifaces: {nic_names}"[:w], curses.color_pair(C_DIM))


def _fill_disk_panel(win, col: Collector, y: int, x: int, h: int, w: int) -> None:
    d = col.data
    disks = d.get("disks", [])
    bar_w = max(6, w - 22)
    rows_left = h
    row = y
    for disk in disks:
        if rows_left <= 0:
            break
        pct = disk["pct"]
        cp = _severity_pair(pct, 80, 90)
        label = disk["mp"]
        if len(label) > 12:
            label = "…" + label[-11:]
        _put(win, row, x, f"{label:<12}", curses.color_pair(C_TEXT))
        _put(win, row, x + 13, _hbar(pct, bar_w), curses.color_pair(cp) | curses.A_BOLD)
        _put(win, row, x + 13 + bar_w + 1, f"{pct:5.1f}%",
             curses.color_pair(cp) | curses.A_BOLD)
        row += 1; rows_left -= 1

    if disks and rows_left > 0:
        total = sum(dd["total"] for dd in disks)
        used  = sum(dd["used"]  for dd in disks)
        _put(win, row, x,
             f"Σ  {used/1024**3:5.1f} / {total/1024**3:5.1f} GB  ·  {len(disks)} mounts",
             curses.color_pair(C_DIM))


def _fill_top_panel(win, col: Collector, y: int, x: int, h: int, w: int) -> None:
    d = col.data
    procs = sorted(d.get("procs", []), key=lambda p: p["cpu"], reverse=True)[:h - 1]
    _put(win, y, x,
         f"{'PID':>7}  {'NAME':<20}  {'USER':<10}  {'CPU%':>6}  {'MEM%':>6}",
         curses.color_pair(C_DIM))
    for i, p in enumerate(procs):
        yy = y + 1 + i
        if yy >= y + h:
            break
        cp = _severity_pair(p["cpu"], 20, 50)
        _put(win, yy, x,
             f"{p['pid']:>7}  {p['name'][:20]:<20}  {p['user'][:10]:<10}  ",
             curses.color_pair(C_TEXT))
        _put(win, yy, x + 7 + 2 + 20 + 2 + 10 + 2,
             f"{p['cpu']:>5.1f}%",
             curses.color_pair(cp) | curses.A_BOLD)
        _put(win, yy, x + 7 + 2 + 20 + 2 + 10 + 2 + 8,
             f"{p['mem']:>5.1f}%",
             curses.color_pair(C_TEXT))


def _view_overview(win, col: Collector, ui: UIState) -> None:
    d = col.data
    H, W = win.getmaxyx()
    if not d:
        _put(win, 4, 2, "  warming up sensors…",
             curses.color_pair(C_DIM) | curses.A_BOLD)
        return

    # available area: rows 3..H-2 (H-4 rows), cols 0..W-1
    y0 = 3
    x0 = 0
    avail_h = max(8, H - y0 - 2)
    avail_w = W - 1

    cpu_load = d["cpu"]
    cpu_meta = f"{cpu_load:4.1f}% · {len(d['cores'])} cores"
    mem_meta = f"{d['mem'].percent:4.1f}% · {d['mem'].used/1024**3:.1f}G"
    net_meta = f"↓{_fmt_rate(d['rx_rate'])} ↑{_fmt_rate(d['tx_rate'])}"
    n_disks  = len(d.get("disks", []))
    disk_meta = f"{n_disks} mounts"
    top_meta = f"top {min(5, len(d.get('procs', [])))} by cpu"

    two_col = avail_w >= 100

    if two_col:
        # 2x2 grid + full-width TOP row — fixed compact header panels,
        # remainder goes to the process list which scales with terminal height.
        col_w = avail_w // 2
        top_h = 7     # CPU, MEM — just enough: header, bar, cores, spark, extras
        mid_h = 7     # NET, DISK
        proc_h = max(5, avail_h - top_h - mid_h)

        yA, xA, hA, wA = _panel(win, y0,               x0,         top_h,  col_w,
                                "CPU",  C_INFO, cpu_meta)
        yB, xB, hB, wB = _panel(win, y0,               x0 + col_w, top_h,  avail_w - col_w,
                                "MEM",  C_INFO, mem_meta)
        yC, xC, hC, wC = _panel(win, y0 + top_h,       x0,         mid_h,  col_w,
                                "NET",  C_INFO, net_meta)
        yD, xD, hD, wD = _panel(win, y0 + top_h,       x0 + col_w, mid_h,  avail_w - col_w,
                                "DISK", C_INFO, disk_meta)
        yE, xE, hE, wE = _panel(win, y0 + top_h+mid_h, x0,         proc_h, avail_w,
                                "TOP PROCESSES", C_INFO, top_meta)
    else:
        # stacked single column
        slices = [("CPU", cpu_meta, 7),
                  ("MEM", mem_meta, 6),
                  ("NET", net_meta, 6),
                  ("DISK", disk_meta, max(4, n_disks + 2)),
                  ("TOP PROCESSES", top_meta, max(6, avail_h - 23))]
        yy = y0
        rects = []
        for name, meta, ph in slices:
            ph = min(ph, max(3, y0 + avail_h - yy))
            if ph < 3: break
            ry, rx, rh, rw = _panel(win, yy, x0, ph, avail_w, name, C_INFO, meta)
            rects.append((name, ry, rx, rh, rw))
            yy += ph
        rect_map = {n: (yy, xx, hh, ww) for n, yy, xx, hh, ww in rects}
        yA, xA, hA, wA = rect_map.get("CPU",  (0, 0, 0, 0))
        yB, xB, hB, wB = rect_map.get("MEM",  (0, 0, 0, 0))
        yC, xC, hC, wC = rect_map.get("NET",  (0, 0, 0, 0))
        yD, xD, hD, wD = rect_map.get("DISK", (0, 0, 0, 0))
        yE, xE, hE, wE = rect_map.get("TOP PROCESSES", (0, 0, 0, 0))

    if hA > 0: _fill_cpu_panel (win, col, yA, xA, hA, wA)
    if hB > 0: _fill_mem_panel (win, col, yB, xB, hB, wB)
    if hC > 0: _fill_net_panel (win, col, yC, xC, hC, wC)
    if hD > 0: _fill_disk_panel(win, col, yD, xD, hD, wD)
    if hE > 0: _fill_top_panel (win, col, yE, xE, hE, wE)


# ── view: processes ───────────────────────────────────────────────────────

def _view_processes(win, col: Collector, ui: UIState) -> None:
    d = col.data
    if not d:
        _put(win, 4, 2, "Loading process list…", curses.color_pair(C_DIM))
        return
    h, w = win.getmaxyx()

    procs = list(d.get("procs", []))
    if ui.proc_filter:
        f = ui.proc_filter.lower()
        procs = [p for p in procs if f in p["name"].lower() or f in str(p["pid"])]

    key = {"cpu": "cpu", "mem": "mem", "pid": "pid", "name": "name"}[ui.proc_sort]
    rev = ui.proc_sort in ("cpu", "mem")
    procs.sort(key=lambda p: p[key], reverse=rev)

    # search bar
    if ui.proc_filter_active or ui.proc_filter:
        prompt = f"  / {ui.proc_filter}"
        if ui.proc_filter_active:
            prompt += "█"
        _put(win, 3, 0, " " * (w - 1), curses.color_pair(C_ACCENT) | curses.A_REVERSE)
        _put(win, 3, 0, prompt, curses.color_pair(C_ACCENT) | curses.A_REVERSE | curses.A_BOLD)
        body_top = 5
    else:
        body_top = 4

    # column headers
    cols = [
        ("PID",   7,  "pid"),
        ("USER",  10, None),
        ("STAT",  6,  None),
        ("NAME",  28, "name"),
        ("CPU%",  7,  "cpu"),
        ("MEM%",  7,  "mem"),
    ]
    x = 2
    for label, wc, key in cols:
        attr = curses.color_pair(C_ACCENT) | curses.A_BOLD if key == ui.proc_sort \
               else curses.color_pair(C_DIM)
        _put(win, body_top, x, label.ljust(wc), attr)
        x += wc + 1
    _hline(win, body_top + 1, 2, w - 4, "─", curses.color_pair(C_DIM))

    visible = max(1, h - body_top - 4)
    total = len(procs)
    ui.proc_idx    = max(0, min(ui.proc_idx, total - 1))
    ui.proc_scroll = max(0, min(ui.proc_scroll, max(0, total - visible)))
    if ui.proc_idx < ui.proc_scroll:
        ui.proc_scroll = ui.proc_idx
    elif ui.proc_idx >= ui.proc_scroll + visible:
        ui.proc_scroll = ui.proc_idx - visible + 1

    for row_i in range(visible):
        idx = ui.proc_scroll + row_i
        if idx >= total:
            break
        p = procs[idx]
        y = body_top + 2 + row_i
        cpair = _severity_pair(p["cpu"], 20, 50)
        sel = idx == ui.proc_idx

        if sel:
            _put(win, y, 0, " " * (w - 1),
                 curses.color_pair(C_ACCENT) | curses.A_REVERSE)
            base = curses.color_pair(C_ACCENT) | curses.A_REVERSE | curses.A_BOLD
        else:
            base = curses.color_pair(C_TEXT)

        _put(win, y, 2,  f"{p['pid']:>7}", base)
        _put(win, y, 10, f" {p['user'][:10]:<10}", base)
        _put(win, y, 21, f" {p['stat'][:6]:<6}", base)
        _put(win, y, 28, f" {p['name'][:28]:<28}", base)
        _put(win, y, 57, f" {p['cpu']:>5.1f}%",
             base if sel else curses.color_pair(cpair) | curses.A_BOLD)
        _put(win, y, 65, f"  {p['mem']:>5.1f}%", base)

    # status line
    sort_label = {"cpu": "CPU", "mem": "MEM", "pid": "PID", "name": "NAME"}[ui.proc_sort]
    ui.footer_info = f"{total} processes · sort {sort_label}"
    if ui.proc_filter:
        ui.footer_info += f" · filter “{ui.proc_filter}”"


# ── view: disk ────────────────────────────────────────────────────────────

def _view_disk(win, col: Collector, ui: UIState) -> None:
    d = col.data
    if not d:
        return
    h, w = win.getmaxyx()
    disks = d.get("disks", [])
    bar_w = max(15, min(w - 60, 40))

    _put(win, 4, 2,
         f"{'MOUNTPOINT':<28}  {'FS':<8}  {'USED':>8}  {'TOTAL':>8}  USAGE",
         curses.color_pair(C_DIM))
    _hline(win, 5, 2, w - 4, "─", curses.color_pair(C_DIM))

    row = 6
    for disk in disks:
        if row >= h - 2:
            break
        pct = disk["pct"]
        cp = _severity_pair(pct, 80, 90)
        mp = disk["mp"][:28]
        _put(win, row, 2,  f"{mp:<28}", curses.color_pair(C_TEXT))
        _put(win, row, 32, f" {disk.get('fs','')[:8]:<8}", curses.color_pair(C_DIM))
        _put(win, row, 42, f" {disk['used']/1024**3:>6.1f}G", curses.color_pair(C_TEXT))
        _put(win, row, 52, f" {disk['total']/1024**3:>6.1f}G", curses.color_pair(C_TEXT))
        _put(win, row, 62, _hbar(pct, bar_w), curses.color_pair(cp) | curses.A_BOLD)
        _put(win, row, 62 + bar_w + 1, f" {pct:5.1f}%",
             curses.color_pair(cp) | curses.A_BOLD)
        row += 1

    # summary
    if disks:
        total = sum(d["total"] for d in disks)
        used  = sum(d["used"]  for d in disks)
        row += 1
        _put(win, row, 2,
             f"  Σ  {used/1024**3:.1f} / {total/1024**3:.1f} GB used"
             f"   ·   {len(disks)} mounts",
             curses.color_pair(C_INFO) | curses.A_BOLD)


# ── view: network ─────────────────────────────────────────────────────────

def _view_net(win, col: Collector, ui: UIState) -> None:
    d = col.data
    if not d:
        return
    h, w = win.getmaxyx()
    rx = d["rx_rate"]; tx = d["tx_rate"]
    _put(win, 4, 2, "Live throughput", curses.color_pair(C_INFO) | curses.A_BOLD)
    _put(win, 5, 4, f"↓ rx  {_fmt_rate(rx):<12}", curses.color_pair(C_OK)  | curses.A_BOLD)
    _put(win, 6, 4, f"↑ tx  {_fmt_rate(tx):<12}", curses.color_pair(C_ACCENT)| curses.A_BOLD)

    spark_w = max(20, w - 12)
    rx_max = max(col.history.rx) if col.history.rx else 1
    tx_max = max(col.history.tx) if col.history.tx else 1
    _put(win, 5, 24, _chart(list(col.history.rx), spark_w - 24, 0, max(rx_max, 1)),
         curses.color_pair(C_OK))
    _put(win, 6, 24, _chart(list(col.history.tx), spark_w - 24, 0, max(tx_max, 1)),
         curses.color_pair(C_ACCENT))
    _put(win, 7, 4,
         f"peak ↓ {_fmt_rate(rx_max)}    peak ↑ {_fmt_rate(tx_max)}",
         curses.color_pair(C_DIM))

    _put(win, 9, 2,
         f"{'IFACE':<14}  {'RX':>10}  {'TX':>10}  {'PKT-RX':>10}  {'PKT-TX':>10}  {'ERRS':>6}  {'DROP':>6}",
         curses.color_pair(C_DIM))
    _hline(win, 10, 2, w - 4, "─", curses.color_pair(C_DIM))
    row = 11
    for nic in d.get("ifaces", []):
        if row >= h - 2:
            break
        _put(win, row, 2,
             f"{nic['name'][:14]:<14}  "
             f"{_fmt_bytes(nic['rx']):>10}  {_fmt_bytes(nic['tx']):>10}  "
             f"{nic['rx_pkts']:>10}  {nic['tx_pkts']:>10}  "
             f"{nic['errs']:>6}  {nic['drop']:>6}",
             curses.color_pair(C_TEXT))
        row += 1


# ── view: alerts ──────────────────────────────────────────────────────────

def _view_alerts(win, alerts: AlertTail, ui: UIState) -> None:
    h, w = win.getmaxyx()
    items = list(reversed(alerts.items))
    if not items:
        _put(win, 5, 2, "  ✓ no alerts in log — system is healthy",
             curses.color_pair(C_OK) | curses.A_BOLD)
        return

    _put(win, 4, 2,
         f"{'TIME':<19}  {'SEV':<8}  {'METRIC':<28}  MESSAGE",
         curses.color_pair(C_DIM))
    _hline(win, 5, 2, w - 4, "─", curses.color_pair(C_DIM))

    visible = max(1, h - 8)
    total = len(items)
    ui.alert_idx = max(0, min(ui.alert_idx, total - 1))
    if ui.alert_idx < ui.alert_scroll:
        ui.alert_scroll = ui.alert_idx
    elif ui.alert_idx >= ui.alert_scroll + visible:
        ui.alert_scroll = ui.alert_idx - visible + 1
    ui.alert_scroll = max(0, min(ui.alert_scroll, max(0, total - visible)))

    for row_i in range(visible):
        idx = ui.alert_scroll + row_i
        if idx >= total:
            break
        a = items[idx]
        y = 6 + row_i
        sev = a.get("severity", "info")
        sev_pair = {"critical": C_CRIT, "warning": C_WARN}.get(sev, C_INFO)
        ts = a.get("timestamp", "")[:19].replace("T", " ")
        metric = a.get("metric_name", "")[:28]
        msg = a.get("message", "")
        sel = idx == ui.alert_idx
        if sel:
            _put(win, y, 0, " " * (w - 1),
                 curses.color_pair(C_ACCENT) | curses.A_REVERSE)
            base = curses.color_pair(C_ACCENT) | curses.A_REVERSE
        else:
            base = curses.color_pair(C_TEXT)
        _put(win, y, 2, f"{ts:<19}  ", base)
        _put(win, y, 23, f"{sev.upper():<8}",
             base if sel else curses.color_pair(sev_pair) | curses.A_BOLD)
        _put(win, y, 33, f"  {metric:<28}  ", base)
        _put(win, y, 65, msg[: max(0, w - 67)], base)

    _put(win, h - 2, 2, f"  {total} alerts · {alerts.path}",
         curses.color_pair(C_DIM))


# ── view: config ──────────────────────────────────────────────────────────

def _view_config(win, cfg: MonitorConfig, ui: UIState) -> None:
    h, w = win.getmaxyx()

    title_attr = curses.color_pair(C_INFO) | curses.A_BOLD
    dirty = " ●" if ui.cfg_dirty else ""
    _put(win, 4, 2, f"Configuration{dirty}", title_attr)
    _put(win, 4, 28, "press ↵ to edit · s to save",
         curses.color_pair(C_DIM))

    if ui.cfg_msg:
        _put(win, 4, w - len(ui.cfg_msg) - 4, ui.cfg_msg,
             curses.color_pair(C_OK) | curses.A_BOLD)

    row = 6
    last_section = ""
    for i, (section, label, path, kind) in enumerate(CONFIG_FIELDS):
        if row >= h - 3:
            break
        if section != last_section:
            _put(win, row, 2, f"▎ {section}",
                 curses.color_pair(C_ACCENT) | curses.A_BOLD)
            row += 1
            last_section = section

        sel = i == ui.cfg_idx
        prefix = "  ▸ " if sel else "    "
        attr = curses.color_pair(C_ACCENT) | curses.A_BOLD if sel else curses.color_pair(C_TEXT)

        if sel:
            _put(win, row, 0, " " * (w - 1),
                 curses.color_pair(C_ACCENT) | curses.A_REVERSE)
            attr = curses.color_pair(C_ACCENT) | curses.A_REVERSE | curses.A_BOLD

        _put(win, row, 2, f"{prefix}{label:<26}", attr)

        try:
            value = _cfg_get(cfg, path)
        except Exception:
            value = None

        if sel and ui.cfg_editing:
            shown = ui.cfg_buffer + "█"
            if ui.cfg_fresh:
                edit_attr = curses.color_pair(C_ACCENT) | curses.A_REVERSE | curses.A_BOLD
            else:
                edit_attr = curses.color_pair(C_TITLE) | curses.A_REVERSE | curses.A_BOLD
            _put(win, row, 32, f" {shown} ", edit_attr)
        else:
            shown = _cfg_display(value, kind)
            v_attr = attr if sel else (
                curses.color_pair(C_OK) if shown.startswith("●")
                else curses.color_pair(C_DIM) if shown.startswith("○") or shown.startswith("(")
                else curses.color_pair(C_TITLE) | curses.A_BOLD
            )
            _put(win, row, 32, f"{shown}", v_attr)

        _put(win, row, w - 12, kind, curses.color_pair(C_DIM))
        row += 1


# ── help overlay ──────────────────────────────────────────────────────────

_HELP = [
    ("Navigation",  "1-6",                   "jump directly to view"),
    ("",            "← / → / h / l / Tab",   "previous / next view"),
    ("",            "↑ / ↓",                 "move selection"),
    ("",            "PgUp / PgDn",           "page selection"),
    ("",            "g / G",                 "first / last"),
    ("",            "q",                     "quit"),
    ("",            "Esc",                   "cancel edit / close overlay"),
    ("Processes",   "/",                     "search"),
    ("",            "s",                     "cycle sort (cpu/mem/pid/name)"),
    ("",            "k",                     "kill selected (SIGTERM, confirms)"),
    ("Config",      "↵",                     "edit value"),
    ("",            "esc",                   "cancel edit"),
    ("",            "s",                     "save to config.yaml"),
    ("Alerts",      "↑↓",                    "scroll history"),
    ("Misc",        "?",                     "this help"),
    ("",            "r",                     "force redraw"),
]


def _draw_help(win) -> None:
    h, w = win.getmaxyx()
    bw = min(70, w - 6)
    bh = min(len(_HELP) + 6, h - 4)
    y0 = (h - bh) // 2
    x0 = (w - bw) // 2

    for y in range(y0, y0 + bh):
        _put(win, y, x0, " " * bw, curses.color_pair(C_TEXT) | curses.A_REVERSE)

    _put(win, y0,        x0 + 2, " HELP — keymap ",
         curses.color_pair(C_ACCENT) | curses.A_REVERSE | curses.A_BOLD)
    _put(win, y0 + bh-1, x0 + 2, " ? close ",
         curses.color_pair(C_DIM) | curses.A_REVERSE)

    last_sec = ""
    y = y0 + 2
    for sec, key, desc in _HELP:
        if y >= y0 + bh - 1:
            break
        if sec and sec != last_sec:
            _put(win, y, x0 + 2, sec,
                 curses.color_pair(C_ACCENT) | curses.A_REVERSE | curses.A_BOLD)
            last_sec = sec
        _put(win, y, x0 + 14, key,
             curses.color_pair(C_TITLE) | curses.A_REVERSE | curses.A_BOLD)
        _put(win, y, x0 + 34, desc,
             curses.color_pair(C_TEXT) | curses.A_REVERSE)
        y += 1


def _draw_confirm(win, prompt: str) -> None:
    h, w = win.getmaxyx()
    bw = min(len(prompt) + 18, w - 6)
    bh = 5
    y0 = (h - bh) // 2
    x0 = (w - bw) // 2
    for y in range(y0, y0 + bh):
        _put(win, y, x0, " " * bw, curses.color_pair(C_CRIT) | curses.A_REVERSE)
    _put(win, y0,     x0 + 2, " confirm ",
         curses.color_pair(C_CRIT) | curses.A_REVERSE | curses.A_BOLD)
    _put(win, y0 + 2, x0 + 2, prompt,
         curses.color_pair(C_TITLE) | curses.A_REVERSE | curses.A_BOLD)
    _put(win, y0 + 4, x0 + 2, " y  yes        n / esc  cancel ",
         curses.color_pair(C_DIM) | curses.A_REVERSE)


# ══════════════════════════════════════════════════════════════════════════
# input handling
# ══════════════════════════════════════════════════════════════════════════

def _kill_pid(pid: int, ui: UIState) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
        ui.push_toast(f"sent SIGTERM to PID {pid}", C_OK)
    except ProcessLookupError:
        ui.push_toast(f"PID {pid} not found", C_WARN)
    except PermissionError:
        ui.push_toast(f"permission denied for PID {pid}", C_CRIT)
    except Exception as e:
        ui.push_toast(f"kill failed: {e}", C_CRIT)


def _handle_processes_key(key: int, win, col: Collector, ui: UIState) -> bool:
    h, _w = win.getmaxyx()
    visible = max(1, h - 8)
    procs = list(col.data.get("procs", []))
    if ui.proc_filter:
        f = ui.proc_filter.lower()
        procs = [p for p in procs if f in p["name"].lower() or f in str(p["pid"])]

    if ui.proc_filter_active:
        if key in (10, 13, curses.KEY_ENTER):
            ui.proc_filter_active = False
        elif key == 27:
            ui.proc_filter_active = False
            ui.proc_filter = ""
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            ui.proc_filter = ui.proc_filter[:-1]
        elif 32 <= key < 127:
            ui.proc_filter += chr(key)
        return True

    if key == ord("/"):
        ui.proc_filter_active = True; return True
    if key == ord("s"):
        order = ["cpu", "mem", "pid", "name"]
        ui.proc_sort = order[(order.index(ui.proc_sort) + 1) % len(order)]
        return True
    if key == ord("k") and procs:
        key_fn = {"cpu": "cpu", "mem": "mem", "pid": "pid", "name": "name"}[ui.proc_sort]
        rev = ui.proc_sort in ("cpu", "mem")
        procs.sort(key=lambda p: p[key_fn], reverse=rev)
        idx = max(0, min(ui.proc_idx, len(procs) - 1))
        target = procs[idx]
        pid = target["pid"]; name = target["name"]
        ui.confirm = (f"Send SIGTERM to {name} (PID {pid})?",
                      lambda: _kill_pid(pid, ui))
        return True
    if key in (curses.KEY_UP, ord("k")):
        ui.proc_idx = max(0, ui.proc_idx - 1); return True
    if key in (curses.KEY_DOWN, ord("j")):
        ui.proc_idx += 1; return True
    if key == curses.KEY_PPAGE:
        ui.proc_idx = max(0, ui.proc_idx - visible); return True
    if key == curses.KEY_NPAGE:
        ui.proc_idx += visible; return True
    if key == ord("g"):
        ui.proc_idx = 0; return True
    if key == ord("G"):
        ui.proc_idx = max(0, len(procs) - 1); return True
    return False


def _handle_alerts_key(key: int, win, ui: UIState) -> bool:
    h, _w = win.getmaxyx()
    visible = max(1, h - 8)
    if key in (curses.KEY_UP, ord("k")):
        ui.alert_idx = max(0, ui.alert_idx - 1); return True
    if key in (curses.KEY_DOWN, ord("j")):
        ui.alert_idx += 1; return True
    if key == curses.KEY_PPAGE:
        ui.alert_idx = max(0, ui.alert_idx - visible); return True
    if key == curses.KEY_NPAGE:
        ui.alert_idx += visible; return True
    if key == ord("g"):
        ui.alert_idx = 0; return True
    return False


def _handle_config_key(key: int, cfg: MonitorConfig, ui: UIState,
                        config_path: str) -> bool:
    if ui.cfg_editing:
        if key in (10, 13, curses.KEY_ENTER):
            section, label, path, kind = CONFIG_FIELDS[ui.cfg_idx]
            try:
                _cfg_set(cfg, path, ui.cfg_buffer, kind)
                ui.cfg_dirty = True
                ui.cfg_msg = f"changed {label} (unsaved)"
            except Exception as e:
                ui.push_toast(f"invalid value: {e}", C_CRIT)
            ui.cfg_editing = False
            ui.cfg_buffer = ""
            return True
        if key == 27:
            ui.cfg_editing = False
            ui.cfg_buffer = ""
            return True
        if key in (curses.KEY_BACKSPACE, 127, 8):
            ui.cfg_buffer = ui.cfg_buffer[:-1]
            ui.cfg_fresh = False
            return True
        if key == 21:  # Ctrl-U  — clear
            ui.cfg_buffer = ""; ui.cfg_fresh = False; return True
        if 32 <= key < 127:
            if ui.cfg_fresh:
                ui.cfg_buffer = ""
                ui.cfg_fresh = False
            ui.cfg_buffer += chr(key)
            return True
        return True

    if key in (curses.KEY_UP, ord("k")):
        ui.cfg_idx = max(0, ui.cfg_idx - 1); return True
    if key in (curses.KEY_DOWN, ord("j")):
        ui.cfg_idx = min(len(CONFIG_FIELDS) - 1, ui.cfg_idx + 1); return True
    if key == ord("g"):
        ui.cfg_idx = 0; return True
    if key == ord("G"):
        ui.cfg_idx = len(CONFIG_FIELDS) - 1; return True
    if key in (10, 13, curses.KEY_ENTER):
        _, _, path, kind = CONFIG_FIELDS[ui.cfg_idx]
        cur = _cfg_get(cfg, path)
        if kind == "bool":
            _cfg_set(cfg, path, "false" if cur else "true", "bool")
            ui.cfg_dirty = True
            ui.cfg_msg = "toggled (unsaved)"
        elif kind == "list":
            ui.cfg_buffer = ", ".join(cur) if cur else ""
            ui.cfg_editing = True
            ui.cfg_fresh = bool(ui.cfg_buffer)
        elif kind == "secret":
            ui.cfg_buffer = ""
            ui.cfg_editing = True
            ui.cfg_fresh = False
        else:
            ui.cfg_buffer = "" if cur in (None, "") else str(cur)
            ui.cfg_editing = True
            ui.cfg_fresh = bool(ui.cfg_buffer)
        return True
    if key == ord("s"):
        try:
            cfg.save(config_path)
            ui.cfg_dirty = False
            ui.cfg_msg = f"saved → {config_path}"
            ui.push_toast(f"config saved → {config_path}", C_OK)
        except Exception as e:
            ui.push_toast(f"save failed: {e}", C_CRIT)
        return True
    return False


# ══════════════════════════════════════════════════════════════════════════
# main loop
# ══════════════════════════════════════════════════════════════════════════

def run_tui(config_path: str = "config.yaml") -> None:
    cfg     = MonitorConfig.load(config_path)
    col     = Collector()
    alerts  = AlertTail(cfg.alerts.log_file)
    ui      = UIState()
    stop_ev = threading.Event()

    worker = threading.Thread(target=col.run, args=(stop_ev,), daemon=True)
    worker.start()

    def _loop(win) -> None:
        curses.curs_set(0)
        win.nodelay(True)
        win.timeout(_POLL_MS)
        win.keypad(True)
        try:
            curses.mousemask(0)
        except curses.error:
            pass
        try:
            curses.set_escdelay(25)
        except (AttributeError, curses.error):
            pass
        _init_colors()
        col.ready.wait(timeout=2.0)
        alerts.refresh()

        last_alert_check = 0.0

        while True:
            key = win.getch()

            # Manual escape-sequence composition. Some terminals (and pty
            # pipelines) deliver `ESC [ X` as three separate reads instead of
            # a single KEY_* code. Stitch them back together here so arrow
            # keys always work regardless of keypad/escdelay quirks.
            if key == 27:
                nxt1 = win.getch()
                if nxt1 == ord('['):
                    nxt2 = win.getch()
                    seq = {ord('A'): curses.KEY_UP,    ord('B'): curses.KEY_DOWN,
                           ord('C'): curses.KEY_RIGHT, ord('D'): curses.KEY_LEFT,
                           ord('H'): curses.KEY_HOME,  ord('F'): curses.KEY_END,
                           ord('5'): curses.KEY_PPAGE, ord('6'): curses.KEY_NPAGE}
                    if nxt2 in seq:
                        key = seq[nxt2]
                        if nxt2 in (ord('5'), ord('6')):
                            win.getch()  # swallow the trailing '~'
                    # else: unknown CSI, fall through with key=27
                elif nxt1 != -1:
                    # alt-<char>: treat as bare ESC and requeue the char
                    try: curses.ungetch(nxt1)
                    except curses.error: pass

            if key != -1:
                # 1. modal overlays consume keys first
                if ui.confirm:
                    if key in (ord("y"), ord("Y")):
                        _, action = ui.confirm
                        ui.confirm = None
                        try: action()
                        except Exception as e: ui.push_toast(f"action failed: {e}", C_CRIT)
                    elif key in (ord("n"), ord("N"), 27):
                        ui.confirm = None
                elif ui.show_help:
                    if key in (ord("?"), 27, ord("q"), ord("Q")):
                        ui.show_help = False

                # 2. text-input modes trap EVERY key (including digits)
                elif ui.view == V_CONFIG and ui.cfg_editing:
                    _handle_config_key(key, cfg, ui, config_path)
                elif ui.view == V_PROCS and ui.proc_filter_active:
                    _handle_processes_key(key, win, col, ui)

                # 3. global keybinds
                elif key in (ord("q"), ord("Q")):
                    break
                elif key == 27:  # esc — no-op outside modal state
                    pass
                elif key == ord("?"):
                    ui.show_help = True
                elif ord("1") <= key <= ord("6"):
                    ui.view = key - ord("1")
                    if ui.view == V_ALERTS:
                        alerts.fresh_count = 0
                elif key in (9, curses.KEY_RIGHT) or key == ord("l"):
                    ui.view = (ui.view + 1) % len(VIEWS)
                    if ui.view == V_ALERTS: alerts.fresh_count = 0
                elif key in (curses.KEY_BTAB, curses.KEY_LEFT) or key == ord("h"):
                    ui.view = (ui.view - 1) % len(VIEWS)
                    if ui.view == V_ALERTS: alerts.fresh_count = 0

                # 4. view-specific handlers
                else:
                    if ui.view == V_PROCS:
                        _handle_processes_key(key, win, col, ui)
                    elif ui.view == V_ALERTS:
                        _handle_alerts_key(key, win, ui)
                    elif ui.view == V_CONFIG:
                        _handle_config_key(key, cfg, ui, config_path)

            # alert tail polling (every ~1s)
            now = time.monotonic()
            if now - last_alert_check > 1.0:
                if alerts.refresh():
                    new = alerts.fresh_count
                    sev = alerts.items[-1].get("severity", "warning") if alerts.items else "warning"
                    pair = C_CRIT if sev == "critical" else C_WARN
                    ui.push_toast(f"{new} new alert(s) · severity {sev}", pair)
                    if ui.view == V_ALERTS:
                        alerts.fresh_count = 0
                last_alert_check = now

            try:
                win.erase()
                _draw_topbar(win, col, alerts, ui)
                _draw_tabs(win, ui, alerts)

                ui.footer_info = ""
                if ui.view == V_OVERVIEW: _view_overview(win, col, ui)
                elif ui.view == V_PROCS:  _view_processes(win, col, ui)
                elif ui.view == V_DISK:   _view_disk(win, col, ui)
                elif ui.view == V_NET:    _view_net(win, col, ui)
                elif ui.view == V_ALERTS: _view_alerts(win, alerts, ui)
                elif ui.view == V_CONFIG: _view_config(win, cfg, ui)

                _draw_toasts(win, ui)
                _draw_footer(win, ui)
                if ui.confirm:
                    _draw_confirm(win, ui.confirm[0])
                if ui.show_help:
                    _draw_help(win)

                win.refresh()
            except curses.error:
                pass

    try:
        curses.wrapper(_loop)
    finally:
        stop_ev.set()
