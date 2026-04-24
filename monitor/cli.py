"""
Simple CLI interface - just 3 modes + service installer.
"""

import os
import sys
import time
import shutil
import argparse
import subprocess
from pathlib import Path

from loguru import logger

from monitor import __version__
from monitor.config import MonitorConfig
from monitor.collector import SystemCollector
from monitor.alerter import AlertManager
from monitor.reporter import Reporter


# Configure logger
logger.remove()  # Remove default handler
logger.add(
    "monitor.log",
    rotation="10 MB",
    retention="7 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
)
logger.add(
    sys.stderr,
    level="WARNING",
    format="<level>{level: <8}</level> | <level>{message}</level>"
)


# ── paths ─────────────────────────────────────────────────────────────────
SERVICE_NAME = "shm"
SERVICE_FILE = f"/etc/systemd/system/{SERVICE_NAME}.service"
CONFIG_DIR   = Path("/etc/shm")
DATA_DIR     = Path("/var/lib/shm")

# Bundled service template lives next to this file
_PKG_DIR     = Path(__file__).resolve().parent
_SERVICE_TPL = _PKG_DIR / "monitor.service"
_DEFAULT_CFG = _PKG_DIR / "config.default.yaml"


# ══════════════════════════════════════════════════════════════════════════
# service installer / uninstaller
# ══════════════════════════════════════════════════════════════════════════

def _require_root(action: str) -> None:
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
        description="Server Health Monitor — lightweight Linux system monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  monitor                    # Interactive TUI (default)
  monitor --daemon           # Background mode (no UI)
  sudo monitor --install     # Install as boot service
  sudo monitor --uninstall   # Remove boot service

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
        default='config.yaml',
        help='Configuration file path (default: config.yaml)'
    )

    args = parser.parse_args()

    # ── service management (no config needed) ─────────────────────────
    if args.install:
        install_service()
        return

    if args.uninstall:
        uninstall_service()
        return

    # ── modes that need a config file ─────────────────────────────────
    if not Path(args.config).exists():
        print(f"❌ Config file not found: {args.config}")
        print(f"💡 Create config.yaml or specify --config")
        sys.exit(1)

    # Daemon mode
    if args.daemon:
        run_daemon(args.config)

    # Default: fast curses TUI (no heavy deps)
    else:
        try:
            from monitor.fast_tui import run_tui
            run_tui(args.config)
        except Exception as e:
            print(f"❌ Error starting TUI: {e}")
            logger.error(f"TUI error: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()
