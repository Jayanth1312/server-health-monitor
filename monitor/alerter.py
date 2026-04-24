"""
Alert system with threshold monitoring and email notifications.
"""

import json
import smtplib
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from monitor.config import MonitorConfig


@dataclass
class Alert:
    """Represents a triggered alert."""
    timestamp: str
    hostname: str
    metric_name: str
    current_value: float
    threshold: float
    severity: str  # 'warning' or 'critical'
    message: str


class AlertManager:
    """Manages threshold checking and alert notifications."""

    def __init__(self, config: MonitorConfig, hostname: str):
        """Initialize the alert manager."""
        self.config = config
        self.hostname = hostname
        self.last_alerts: Dict[str, datetime] = {}  # metric_name -> last alert time
        self.alert_log_path = Path(config.alerts.log_file)

    def check_thresholds(self, metrics: Dict) -> List[Alert]:
        """Check all metrics against configured thresholds."""
        alerts = []

        if not self.config.alerts.enabled:
            return alerts

        # Check CPU threshold
        cpu_percent = metrics.get('cpu', {}).get('percent_total', 0)
        if cpu_percent > self.config.thresholds.cpu_percent:
            alert = Alert(
                timestamp=datetime.now().isoformat(),
                hostname=self.hostname,
                metric_name='cpu_percent',
                current_value=cpu_percent,
                threshold=self.config.thresholds.cpu_percent,
                severity='critical' if cpu_percent > 95 else 'warning',
                message=f'CPU usage is {cpu_percent:.1f}% (threshold: {self.config.thresholds.cpu_percent}%)'
            )
            alerts.append(alert)

        # Check memory threshold
        memory_percent = metrics.get('memory', {}).get('percent', 0)
        if memory_percent > self.config.thresholds.memory_percent:
            alert = Alert(
                timestamp=datetime.now().isoformat(),
                hostname=self.hostname,
                metric_name='memory_percent',
                current_value=memory_percent,
                threshold=self.config.thresholds.memory_percent,
                severity='critical' if memory_percent > 95 else 'warning',
                message=f'Memory usage is {memory_percent:.1f}% (threshold: {self.config.thresholds.memory_percent}%)'
            )
            alerts.append(alert)

        # Check swap threshold
        swap_percent = metrics.get('memory', {}).get('swap_percent', 0)
        if swap_percent > self.config.thresholds.swap_percent:
            alert = Alert(
                timestamp=datetime.now().isoformat(),
                hostname=self.hostname,
                metric_name='swap_percent',
                current_value=swap_percent,
                threshold=self.config.thresholds.swap_percent,
                severity='warning',
                message=f'Swap usage is {swap_percent:.1f}% (threshold: {self.config.thresholds.swap_percent}%)'
            )
            alerts.append(alert)

        # Check disk thresholds for all partitions
        partitions = metrics.get('disk', {}).get('partitions', [])
        for partition in partitions:
            disk_percent = partition.get('percent', 0)
            mountpoint = partition.get('mountpoint', 'unknown')

            if disk_percent > self.config.thresholds.disk_percent:
                alert = Alert(
                    timestamp=datetime.now().isoformat(),
                    hostname=self.hostname,
                    metric_name=f'disk_percent_{mountpoint}',
                    current_value=disk_percent,
                    threshold=self.config.thresholds.disk_percent,
                    severity='critical' if disk_percent > 98 else 'warning',
                    message=f'Disk usage on {mountpoint} is {disk_percent:.1f}% (threshold: {self.config.thresholds.disk_percent}%)'
                )
                alerts.append(alert)

        return alerts

    def should_send_alert(self, metric_name: str) -> bool:
        """Check if alert should be sent based on cooldown period."""
        if metric_name not in self.last_alerts:
            return True

        cooldown = timedelta(minutes=self.config.alerts.cooldown_minutes)
        elapsed = datetime.now() - self.last_alerts[metric_name]

        return elapsed >= cooldown

    def process_alerts(self, alerts: List[Alert]):
        """Process alerts: log and send notifications."""
        for alert in alerts:
            # Log the alert
            self.log_alert(alert)

            # Check cooldown and send email if enabled
            if self.should_send_alert(alert.metric_name):
                if self.config.smtp.enabled:
                    try:
                        self.send_email(alert)
                        logger.info(f"Email alert sent for {alert.metric_name}")
                    except Exception as e:
                        logger.error(f"Failed to send email alert: {e}")

                # Update last alert time
                self.last_alerts[alert.metric_name] = datetime.now()
            else:
                logger.debug(f"Alert {alert.metric_name} in cooldown period, skipping email")

    def send_email(self, alert: Alert):
        """Send email notification via SMTP."""
        if not self.config.smtp.enabled:
            return

        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[{alert.severity.upper()}] {alert.hostname} - {alert.metric_name}"
        msg['From'] = self.config.smtp.from_addr
        msg['To'] = ', '.join(self.config.smtp.to_addrs)

        # Create plain text body
        text_body = f"""
Server Health Monitor Alert

Server: {alert.hostname}
Metric: {alert.metric_name}
Current Value: {alert.current_value:.2f}%
Threshold: {alert.threshold:.2f}%
Severity: {alert.severity.upper()}
Time: {alert.timestamp}

Message: {alert.message}

---
This is an automated alert from Server Health Monitor.
"""

        # Create HTML body
        html_body = f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: {'#d32f2f' if alert.severity == 'critical' else '#f57c00'};">
      Server Health Monitor Alert
    </h2>
    <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
      <tr>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Server</strong></td>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{alert.hostname}</td>
      </tr>
      <tr>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Metric</strong></td>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{alert.metric_name}</td>
      </tr>
      <tr>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Current Value</strong></td>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{alert.current_value:.2f}%</td>
      </tr>
      <tr>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Threshold</strong></td>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{alert.threshold:.2f}%</td>
      </tr>
      <tr>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Severity</strong></td>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;">
          <span style="color: {'#d32f2f' if alert.severity == 'critical' else '#f57c00'}; font-weight: bold;">
            {alert.severity.upper()}
          </span>
        </td>
      </tr>
      <tr>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Time</strong></td>
        <td style="padding: 8px; border-bottom: 1px solid #ddd;">{alert.timestamp}</td>
      </tr>
    </table>
    <p style="margin-top: 20px; padding: 15px; background-color: #f5f5f5; border-left: 4px solid #2196F3;">
      <strong>Message:</strong> {alert.message}
    </p>
    <p style="color: #666; font-size: 12px; margin-top: 30px;">
      This is an automated alert from Server Health Monitor.
    </p>
  </body>
</html>
"""

        # Attach both versions
        part1 = MIMEText(text_body, 'plain')
        part2 = MIMEText(html_body, 'html')
        msg.attach(part1)
        msg.attach(part2)

        # Send email
        try:
            with smtplib.SMTP(self.config.smtp.host, self.config.smtp.port, timeout=10) as server:
                if self.config.smtp.use_tls:
                    server.starttls()

                if self.config.smtp.username and self.config.smtp.password:
                    server.login(self.config.smtp.username, self.config.smtp.password)

                server.send_message(msg)

            logger.info(f"Alert email sent successfully to {', '.join(self.config.smtp.to_addrs)}")

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email: {e}")
            raise
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            raise

    def log_alert(self, alert: Alert):
        """Append alert to JSONL log file."""
        try:
            # Create log file if it doesn't exist
            if not self.alert_log_path.exists():
                self.alert_log_path.touch()

            # Append alert
            with open(self.alert_log_path, 'a') as f:
                f.write(json.dumps(asdict(alert)) + '\n')

            logger.info(f"Alert logged: {alert.metric_name} = {alert.current_value:.1f}% (threshold: {alert.threshold:.1f}%)")

        except Exception as e:
            logger.error(f"Error logging alert: {e}")

    def get_recent_alerts(self, limit: int = 20) -> List[Alert]:
        """Read recent alerts from log file."""
        try:
            if not self.alert_log_path.exists():
                return []

            alerts = []
            with open(self.alert_log_path, 'r') as f:
                lines = f.readlines()

            # Get last N lines
            for line in lines[-limit:]:
                try:
                    data = json.loads(line.strip())
                    alerts.append(Alert(**data))
                except json.JSONDecodeError:
                    continue

            return list(reversed(alerts))  # Most recent first

        except Exception as e:
            logger.error(f"Error reading alerts: {e}")
            return []

    def clear_cooldowns(self):
        """Clear all cooldown timers (useful for testing)."""
        self.last_alerts.clear()
        logger.info("All alert cooldowns cleared")
