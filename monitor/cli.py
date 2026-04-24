"""
Simple CLI interface - just 3 modes + service installer.
"""

import os
import sys
import time
import shutil
import argparse
import platform
import subprocess
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS   = platform.system() == "Darwin"
IS_LINUX   = platform.system() == "Linux"

from loguru import logger

from monitor import __version__
from monitor.config import MonitorConfig
from monitor.collector import SystemCollector
from monitor.alerter import AlertManager
from monitor.reporter import Reporter


# ── log path ──────────────────────────────────────────────────────────────
# Never use a relative path — the CLI can be launched from any cwd (e.g. a
# read-only mount like /mnt/c on WSL), which would crash at import time.
def _resolve_log_path() -> Path:
    # Explicit override wins
    override = os.environ.get("SHM_LOG_FILE")
    if override:
        return Path(override).expanduser()

    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "SHM" / "monitor.log"

    if IS_MACOS:
        return Path.home() / "Library" / "Logs" / "shm" / "monitor.log"

    # Linux: root → system dir, user → XDG state
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return Path("/var/log/shm/monitor.log")
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "shm" / "monitor.log"


def _setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level="WARNING",
        format="<level>{level: <8}</level> | <level>{message}</level>",
    )
    log_path = _resolve_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(log_path),
            rotation="10 MB",
            retention="7 days",
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        )
    except (OSError, PermissionError) as e:
        # File logging is best-effort — stderr handler still works.
        print(f"⚠  File logging disabled ({log_path}): {e}", file=sys.stderr)


_setup_logging()


# ── paths ─────────────────────────────────────────────────────────────────
SERVICE_NAME = "shm"
SERVICE_FILE = f"/etc/systemd/system/{SERVICE_NAME}.service"
CONFIG_DIR   = Path("/etc/shm")
DATA_DIR     = Path("/var/lib/shm")

# Bundled service template lives next to this file
_PKG_DIR     = Path(__file__).resolve().parent
_SERVICE_TPL = _PKG_DIR / "monitor.service"
_DEFAULT_CFG = _PKG_DIR / "config.default.yaml"


# ── config path resolution ────────────────────────────────────────────────
def _user_config_path() -> Path:
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "SHM" / "config.yaml"
    if IS_MACOS:
        return Path.home() / "Library" / "Application Support" / "shm" / "config.yaml"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "shm" / "config.yaml"


def _resolve_config_path(explicit):
    """Find an existing config, or create a default user config on first run."""
    if explicit:
        p = Path(explicit).expanduser()
        if not p.exists():
            print(f"❌ Config file not found: {p}")
            sys.exit(1)
        return p

    candidates = [Path.cwd() / "config.yaml", _user_config_path()]
    if IS_LINUX:
        candidates.append(Path("/etc/shm/config.yaml"))
    for c in candidates:
        if c.exists():
            return c

    dest = _user_config_path()
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if _DEFAULT_CFG.exists():
            shutil.copy2(_DEFAULT_CFG, dest)
        else:
            MonitorConfig().save(dest)
        print(f"ℹ  No config found — created default at {dest}")
        print(f"   Edit it to set SMTP credentials and thresholds.")
        return dest
    except (OSError, PermissionError) as e:
        print(f"❌ Could not create default config at {dest}: {e}")
        print(f"💡 Pass --config /path/to/config.yaml or create one manually.")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════
# service installer / uninstaller
# ══════════════════════════════════════════════════════════════════════════

def _require_linux(action: str) -> None:
    if not IS_LINUX:
        print(f"❌  '{action}' is Linux-only (uses systemd).")
        print(f"    On {platform.system()}, run the daemon in the foreground instead:")
        print(f"        monitor --daemon")
        print(f"    Or set up your OS-native startup mechanism (Task Scheduler / launchd).")
        sys.exit(1)


def _require_root(action: str) -> None:
    _require_linux(action)
    if os.geteuid() != 0:
        print(f"❌  '{action}' requires root.  Run with sudo:")
        print(f"    sudo monitor {action}")
        sys.exit(1)


def _find_monitor_bin() -> str:
    """Return the absolute path of the 'monitor' executable."""
    path = shutil.which("monitor")
    if not path:
        print("❌  'monitor' command not found in PATH.")
        print("    Install the package first:  pip install server-health-monitor")
        sys.exit(1)
    return path


def install_service() -> None:
    """Install SHM as a systemd service that starts on boot."""
    _require_root("--install")
    monitor_bin = _find_monitor_bin()

    # 1. Create directories
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Copy default config if missing
    cfg_dest = CONFIG_DIR / "config.yaml"
    if not cfg_dest.exists():
        if _DEFAULT_CFG.exists():
            shutil.copy2(_DEFAULT_CFG, cfg_dest)
            print(f"✔  Default config → {cfg_dest}")
        else:
            # Generate a minimal default from the model
            cfg = MonitorConfig()
            cfg.save(cfg_dest)
            print(f"✔  Generated default config → {cfg_dest}")
    else:
        print(f"ℹ  Config already exists at {cfg_dest} — keeping it.")

    # 3. Write systemd unit — dynamically patch the ExecStart path
    if _SERVICE_TPL.exists():
        unit = _SERVICE_TPL.read_text()
    else:
        # Fallback: generate inline
        unit = _generate_service_unit()

    unit = unit.replace(
        "ExecStart=/usr/local/bin/monitor",
        f"ExecStart={monitor_bin}",
    )
    Path(SERVICE_FILE).write_text(unit)
    print(f"✔  Service unit → {SERVICE_FILE}")

    # 4. Enable & start
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", SERVICE_NAME], check=True)
    subprocess.run(["systemctl", "start", SERVICE_NAME], check=True)

    print(f"\n🚀  SHM daemon installed and running!")
    print()
    print("  Useful commands:")
    print(f"    sudo systemctl status {SERVICE_NAME}       # check status")
    print(f"    sudo journalctl -u {SERVICE_NAME} -f       # live logs")
    print(f"    sudo nano {cfg_dest}                       # edit config")
    print(f"    sudo systemctl restart {SERVICE_NAME}      # apply config changes")
    print(f"    sudo monitor --uninstall                   # remove service")
    print()
    print(f"  Edit {cfg_dest} to set your SMTP credentials and thresholds,")
    print(f"  then run: sudo systemctl restart {SERVICE_NAME}")


def uninstall_service() -> None:
    """Remove the SHM systemd service."""
    _require_root("--uninstall")

    subprocess.run(["systemctl", "stop", SERVICE_NAME],
                   capture_output=True)
    subprocess.run(["systemctl", "disable", SERVICE_NAME],
                   capture_output=True)

    svc = Path(SERVICE_FILE)
    if svc.exists():
        svc.unlink()

    subprocess.run(["systemctl", "daemon-reload"], check=True)

    print(f"✔  Service '{SERVICE_NAME}' removed.")
    print(f"   Config and data in {CONFIG_DIR} / {DATA_DIR} were kept.")


def _generate_service_unit() -> str:
    """Fallback: generate the systemd unit text inline."""
    return f"""\
[Unit]
Description=Server Health Monitor — background alerting daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/monitor --daemon --config /etc/shm/config.yaml
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal
WorkingDirectory=/var/lib/shm

NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
"""


# ══════════════════════════════════════════════════════════════════════════
# daemon mode
# ══════════════════════════════════════════════════════════════════════════

def run_daemon(config_path: str):
    """Run in background daemon mode (no UI, just logging and alerts)."""
    try:
        # Load configuration
        config = MonitorConfig.load(config_path)

        # Create components
        collector = SystemCollector()
        reporter = Reporter(config)
        alert_manager = AlertManager(config, collector.hostname)

        logger.info("Starting daemon mode")
        print("🚀 Server Health Monitor Daemon Started")
        print(f"   Hostname: {collector.hostname}")
        print(f"   Interval: {config.collection_interval}s")
        print(f"   Metrics log: {config.metrics_log}")
        print(f"   Alerts: {'enabled' if config.alerts.enabled else 'disabled'}")
        print("\nPress Ctrl+C to stop\n")

        iteration = 0

        while True:
            try:
                # Collect metrics
                metrics = collector.collect_all()

                # Log metrics
                reporter.append_metrics_json(metrics)

                # Check alerts
                if config.alerts.enabled:
                    alerts = alert_manager.check_thresholds(metrics)
                    if alerts:
                        alert_manager.process_alerts(alerts)

                # Rotate logs periodically
                if iteration % 100 == 0:
                    reporter.rotate_logs(max_lines=10000)

                iteration += 1
                time.sleep(config.collection_interval)

            except Exception as e:
                logger.error(f"Error in daemon loop: {e}")
                time.sleep(config.collection_interval)

    except KeyboardInterrupt:
        print("\n✋ Daemon stopped by user")
        logger.info("Daemon stopped by user interrupt")
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        print("💡 Create a config.yaml file first")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error in daemon mode: {e}")
        logger.error(f"Daemon error: {e}")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════
# entry point
# ══════════════════════════════════════════════════════════════════════════

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Server Health Monitor — lightweight cross-platform system monitor (Linux, macOS, Windows)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  monitor                              # Interactive TUI (default)
  monitor --daemon                     # Background mode (no UI)
  monitor --config ~/my-config.yaml    # Use a specific config file
  sudo monitor --install               # Install as boot service
  sudo monitor --uninstall             # Remove boot service

Config search order (first found wins):
  1. --config <path>                (explicit)
  2. ./config.yaml                  (current directory)
  3. ~/.config/shm/config.yaml      (user config)
  4. /etc/shm/config.yaml           (system config, used by service)
If none exist, a default is auto-created at ~/.config/shm/config.yaml.

TUI keys:
  1-6 / Tab     switch view (Overview, Processes, Disk, Network, Alerts, Config)
  ↑↓ PgUp PgDn  navigate    g/G  jump first/last
  /             search processes      s   cycle sort / save config
  k             kill selected process (with confirm)
  ↵             edit config field     esc cancel
  ?             show keymap           q   quit
        """
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'Server Health Monitor v{__version__}'
    )

    parser.add_argument(
        '--daemon', '-d',
        action='store_true',
        help='Run in background mode (no UI)'
    )

    parser.add_argument(
        '--install',
        action='store_true',
        help='Install SHM as a systemd service (requires sudo)'
    )

    parser.add_argument(
        '--uninstall',
        action='store_true',
        help='Remove the SHM systemd service (requires sudo)'
    )

    parser.add_argument(
        '--config', '-c',
        default=None,
        help='Path to config.yaml (default: auto-search, auto-create if missing)'
    )

    args = parser.parse_args()

    # ── service management (no config needed) ─────────────────────────
    if args.install:
        install_service()
        return

    if args.uninstall:
        uninstall_service()
        return

    # ── resolve config path ───────────────────────────────────────────
    config_path = _resolve_config_path(args.config)

    # Daemon mode
    if args.daemon:
        run_daemon(str(config_path))

    # Default: fast curses TUI (no heavy deps)
    else:
        try:
            from monitor.fast_tui import run_tui
            run_tui(str(config_path))
        except Exception as e:
            print(f"❌ Error starting TUI: {e}")
            logger.error(f"TUI error: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()
