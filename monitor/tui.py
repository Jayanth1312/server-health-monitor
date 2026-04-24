"""
Interactive Terminal UI using Textual.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, TabbedContent, TabPane, Button, Label, Input, DataTable
from textual.binding import Binding
from textual.reactive import reactive
from loguru import logger

from monitor.collector import SystemCollector
from monitor.config import MonitorConfig
from monitor.alerter import AlertManager
from monitor.reporter import Reporter


class MetricCard(Static):
    """A card displaying a single metric with color coding."""

    value = reactive(0.0)
    threshold = reactive(85.0)

    def __init__(self, title: str, unit: str = "%", **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.unit = unit

    def render(self) -> str:
        """Render the metric card."""
        # Determine color based on threshold
        if self.value >= self.threshold:
            color = "red"
        elif self.value >= self.threshold * 0.8:
            color = "yellow"
        else:
            color = "green"

        return f"[bold]{self.title}[/bold]\n[{color}]{self.value:.1f}{self.unit}[/{color}]"


class CPUTab(Static):
    """CPU metrics display."""

    def __init__(self, collector: SystemCollector, config: MonitorConfig):
        super().__init__()
        self.collector = collector
        self.config = config

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        with Vertical():
            yield Label("[bold cyan]CPU Usage[/bold cyan]")
            yield MetricCard("Overall CPU", "%", id="cpu-overall")
            yield Label("[bold cyan]Load Average[/bold cyan]", id="load-avg")
            yield Label("[bold cyan]Top Processes[/bold cyan]")
            yield DataTable(id="cpu-processes")

    def on_mount(self) -> None:
        """Initialize the data table."""
        table = self.query_one("#cpu-processes", DataTable)
        table.add_columns("PID", "Name", "CPU %")

    async def update_metrics(self):
        """Update CPU metrics."""
        metrics = self.collector.collect_cpu()

        # Update overall CPU
        cpu_card = self.query_one("#cpu-overall", MetricCard)
        cpu_card.value = metrics.percent_total
        cpu_card.threshold = self.config.thresholds.cpu_percent

        # Update load average
        load_label = self.query_one("#load-avg", Label)
        load_label.update(
            f"[bold cyan]Load Average:[/bold cyan] "
            f"{metrics.load_average[0]:.2f}, {metrics.load_average[1]:.2f}, {metrics.load_average[2]:.2f}"
        )

        # Update process table
        table = self.query_one("#cpu-processes", DataTable)
        table.clear()
        for proc in metrics.top_processes[:5]:
            table.add_row(
                str(proc.get('pid', 'N/A')),
                proc.get('name', 'unknown')[:20],
                f"{proc.get('cpu_percent', 0):.1f}%"
            )


class MemoryTab(Static):
    """Memory metrics display."""

    def __init__(self, collector: SystemCollector, config: MonitorConfig):
        super().__init__()
        self.collector = collector
        self.config = config

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        with Vertical():
            yield Label("[bold cyan]Memory Usage[/bold cyan]")
            yield MetricCard("RAM Usage", "%", id="mem-usage")
            yield Label("", id="mem-details")
            yield Label("[bold cyan]Swap Usage[/bold cyan]")
            yield MetricCard("Swap", "%", id="swap-usage")

    async def update_metrics(self):
        """Update memory metrics."""
        metrics = self.collector.collect_memory()

        # Update RAM
        mem_card = self.query_one("#mem-usage", MetricCard)
        mem_card.value = metrics.percent
        mem_card.threshold = self.config.thresholds.memory_percent

        # Update details
        total_gb = metrics.total / (1024**3)
        used_gb = metrics.used / (1024**3)
        avail_gb = metrics.available / (1024**3)

        details = self.query_one("#mem-details", Label)
        details.update(
            f"Total: {total_gb:.1f} GB | Used: {used_gb:.1f} GB | Available: {avail_gb:.1f} GB"
        )

        # Update swap
        swap_card = self.query_one("#swap-usage", MetricCard)
        swap_card.value = metrics.swap_percent
        swap_card.threshold = self.config.thresholds.swap_percent


class DiskTab(Static):
    """Disk metrics display."""

    def __init__(self, collector: SystemCollector, config: MonitorConfig):
        super().__init__()
        self.collector = collector
        self.config = config

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        with Vertical():
            yield Label("[bold cyan]Disk Usage[/bold cyan]")
            yield DataTable(id="disk-table")

    def on_mount(self) -> None:
        """Initialize the data table."""
        table = self.query_one("#disk-table", DataTable)
        table.add_columns("Mount Point", "Total", "Used", "Usage %")

    async def update_metrics(self):
        """Update disk metrics."""
        metrics = self.collector.collect_disk()

        table = self.query_one("#disk-table", DataTable)
        table.clear()

        for partition in metrics.partitions:
            total_gb = partition['total'] / (1024**3)
            used_gb = partition['used'] / (1024**3)
            percent = partition['percent']

            # Color code the usage percentage
            if percent >= self.config.thresholds.disk_percent:
                color = "red"
            elif percent >= self.config.thresholds.disk_percent * 0.8:
                color = "yellow"
            else:
                color = "green"

            table.add_row(
                partition['mountpoint'],
                f"{total_gb:.1f} GB",
                f"{used_gb:.1f} GB",
                f"[{color}]{percent:.1f}%[/{color}]"
            )


class NetworkTab(Static):
    """Network metrics display."""

    def __init__(self, collector: SystemCollector):
        super().__init__()
        self.collector = collector

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        with Vertical():
            yield Label("[bold cyan]Network Interfaces[/bold cyan]")
            yield DataTable(id="network-table")
            yield Label("", id="network-stats")

    def on_mount(self) -> None:
        """Initialize the data table."""
        table = self.query_one("#network-table", DataTable)
        table.add_columns("Interface", "Sent", "Received", "Errors")

    async def update_metrics(self):
        """Update network metrics."""
        metrics = self.collector.collect_network()

        table = self.query_one("#network-table", DataTable)
        table.clear()

        for interface in metrics.interfaces[:8]:
            sent_mb = interface['bytes_sent'] / (1024**2)
            recv_mb = interface['bytes_recv'] / (1024**2)
            errors = interface['errin'] + interface['errout']

            table.add_row(
                interface['name'],
                f"{sent_mb:.1f} MB",
                f"{recv_mb:.1f} MB",
                f"{errors}"
            )

        # Update connection stats
        stats = self.query_one("#network-stats", Label)
        ports_str = ", ".join(str(p) for p in metrics.listening_ports[:10])
        if len(metrics.listening_ports) > 10:
            ports_str += f" (+{len(metrics.listening_ports) - 10} more)"

        stats.update(
            f"[bold]Connections:[/bold] {metrics.connections} | "
            f"[bold]Listening Ports:[/bold] {ports_str}"
        )


class AlertsTab(Static):
    """Alerts display."""

    def __init__(self, alert_manager: AlertManager):
        super().__init__()
        self.alert_manager = alert_manager

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        with Vertical():
            yield Label("[bold cyan]Recent Alerts[/bold cyan]")
            yield DataTable(id="alerts-table")

    def on_mount(self) -> None:
        """Initialize the data table."""
        table = self.query_one("#alerts-table", DataTable)
        table.add_columns("Time", "Metric", "Value", "Threshold", "Severity")

    async def update_alerts(self):
        """Update alerts display."""
        recent_alerts = self.alert_manager.get_recent_alerts(limit=20)

        table = self.query_one("#alerts-table", DataTable)
        table.clear()

        for alert in recent_alerts:
            # Format timestamp
            timestamp = alert.timestamp.split('.')[0].split('T')
            time_str = f"{timestamp[1]}" if len(timestamp) > 1 else alert.timestamp

            # Color code severity
            severity_color = "red" if alert.severity == "critical" else "yellow"

            table.add_row(
                time_str,
                alert.metric_name,
                f"{alert.current_value:.1f}%",
                f"{alert.threshold:.1f}%",
                f"[{severity_color}]{alert.severity.upper()}[/{severity_color}]"
            )


class ConfigTab(Static):
    """Configuration display and editing."""

    def __init__(self, config: MonitorConfig, config_path: str):
        super().__init__()
        self.config = config
        self.config_path = config_path

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        with Vertical():
            yield Label("[bold cyan]Thresholds Configuration[/bold cyan]")
            yield Label(f"CPU Threshold: {self.config.thresholds.cpu_percent}%", id="cpu-threshold")
            yield Label(f"Memory Threshold: {self.config.thresholds.memory_percent}%", id="mem-threshold")
            yield Label(f"Disk Threshold: {self.config.thresholds.disk_percent}%", id="disk-threshold")
            yield Label(f"Swap Threshold: {self.config.thresholds.swap_percent}%", id="swap-threshold")
            yield Label("")
            yield Label("[bold cyan]Settings[/bold cyan]")
            yield Label(f"Collection Interval: {self.config.collection_interval}s")
            yield Label(f"Alerts Enabled: {self.config.alerts.enabled}")
            yield Label(f"SMTP Enabled: {self.config.smtp.enabled}")
            yield Label("")
            yield Label("[dim]Press 'e' to edit config file[/dim]")

    async def update_config(self):
        """Reload and update configuration display."""
        self.query_one("#cpu-threshold", Label).update(
            f"CPU Threshold: {self.config.thresholds.cpu_percent}%"
        )
        self.query_one("#mem-threshold", Label).update(
            f"Memory Threshold: {self.config.thresholds.memory_percent}%"
        )
        self.query_one("#disk-threshold", Label).update(
            f"Disk Threshold: {self.config.thresholds.disk_percent}%"
        )
        self.query_one("#swap-threshold", Label).update(
            f"Swap Threshold: {self.config.thresholds.swap_percent}%"
        )


class MonitorTUI(App):
    """Interactive terminal UI for server health monitoring."""

    CSS = """
    Screen {
        background: $background;
    }

    Header {
        background: $primary;
        color: $text;
    }

    Footer {
        background: $primary-darken-2;
    }

    MetricCard {
        border: solid $primary;
        padding: 1 2;
        margin: 1;
        width: auto;
        height: auto;
    }

    DataTable {
        height: auto;
        margin: 1;
    }

    Label {
        margin: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("r", "generate_report", "Generate Report"),
        Binding("e", "edit_config", "Edit Config"),
        Binding("d", "toggle_dark", "Toggle Dark Mode"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__()
        self.config_path = config_path
        self.config = MonitorConfig.load(config_path)
        self.collector = SystemCollector()
        self.alert_manager = AlertManager(self.config, self.collector.hostname)
        self.reporter = Reporter(self.config)
        self.update_task = None

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header(show_clock=True)

        with TabbedContent():
            with TabPane("CPU", id="tab-cpu"):
                yield CPUTab(self.collector, self.config)

            with TabPane("Memory", id="tab-memory"):
                yield MemoryTab(self.collector, self.config)

            with TabPane("Disk", id="tab-disk"):
                yield DiskTab(self.collector, self.config)

            with TabPane("Network", id="tab-network"):
                yield NetworkTab(self.collector)

            with TabPane("Alerts", id="tab-alerts"):
                yield AlertsTab(self.alert_manager)

            with TabPane("Config", id="tab-config"):
                yield ConfigTab(self.config, self.config_path)

        yield Footer()

    def on_mount(self) -> None:
        """Start the update loop when app is mounted."""
        self.title = f"Server Health Monitor - {self.collector.hostname}"
        self.sub_title = f"Refresh: {self.config.collection_interval}s"
        self.update_task = self.set_interval(
            self.config.collection_interval,
            self.update_all_metrics
        )

    async def update_all_metrics(self):
        """Update all metric displays."""
        try:
            # Update each tab
            cpu_tab = self.query_one("#tab-cpu CPUTab", CPUTab)
            await cpu_tab.update_metrics()

            mem_tab = self.query_one("#tab-memory MemoryTab", MemoryTab)
            await mem_tab.update_metrics()

            disk_tab = self.query_one("#tab-disk DiskTab", DiskTab)
            await disk_tab.update_metrics()

            network_tab = self.query_one("#tab-network NetworkTab", NetworkTab)
            await network_tab.update_metrics()

            alerts_tab = self.query_one("#tab-alerts AlertsTab", AlertsTab)
            await alerts_tab.update_alerts()

            config_tab = self.query_one("#tab-config ConfigTab", ConfigTab)
            await config_tab.update_config()

            # Check for alerts in background
            metrics = self.collector.collect_all()
            alerts = self.alert_manager.check_thresholds(metrics)
            if alerts:
                self.alert_manager.process_alerts(alerts)

            # Log metrics
            self.reporter.append_metrics_json(metrics)

        except Exception as e:
            logger.error(f"Error updating metrics: {e}")

    def action_generate_report(self):
        """Generate a JSON report."""
        try:
            filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            self.reporter.save_json_snapshot(self.collector, filename)
            self.notify(f"Report saved: {filename}", severity="information")
            logger.info(f"Report generated: {filename}")
        except Exception as e:
            self.notify(f"Error generating report: {e}", severity="error")
            logger.error(f"Report generation failed: {e}")

    def action_edit_config(self):
        """Open config file in editor."""
        import os
        editor = os.environ.get('EDITOR', 'nano')
        self.app.suspend()
        os.system(f"{editor} {self.config_path}")
        # Reload config
        self.config = MonitorConfig.load(self.config_path)
        self.notify("Configuration reloaded", severity="information")

    def action_toggle_dark(self):
        """Toggle dark mode."""
        self.dark = not self.dark


def run_tui(config_path: str = "config.yaml"):
    """Run the interactive TUI."""
    app = MonitorTUI(config_path)
    app.run()
