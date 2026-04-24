"""
Metrics reporting and export functionality.
"""

import json
import csv
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

from loguru import logger

from monitor.config import MonitorConfig
from monitor.collector import SystemCollector


class Reporter:
    """Handles metrics logging and report generation."""

    def __init__(self, config: MonitorConfig):
        """Initialize the reporter."""
        self.config = config
        self.metrics_log_path = Path(config.metrics_log)

    def append_metrics_json(self, metrics: Dict[str, Any]):
        """Append metrics snapshot to JSONL log file."""
        try:
            # Create log file if it doesn't exist
            if not self.metrics_log_path.exists():
                self.metrics_log_path.touch()

            # Append metrics as single JSON line
            with open(self.metrics_log_path, 'a') as f:
                f.write(json.dumps(metrics) + '\n')

            logger.debug(f"Metrics logged to {self.metrics_log_path}")

        except Exception as e:
            logger.error(f"Error logging metrics: {e}")

    def generate_json_snapshot(self, collector: SystemCollector) -> str:
        """Generate a single point-in-time JSON report."""
        try:
            metrics = collector.collect_all()

            # Add additional metadata
            metrics['report_generated'] = datetime.now().isoformat()
            metrics['report_type'] = 'snapshot'

            return json.dumps(metrics, indent=2)

        except Exception as e:
            logger.error(f"Error generating JSON snapshot: {e}")
            raise

    def save_json_snapshot(self, collector: SystemCollector, output_file: str):
        """Save JSON snapshot to file."""
        try:
            json_data = self.generate_json_snapshot(collector)

            with open(output_file, 'w') as f:
                f.write(json_data)

            logger.info(f"JSON snapshot saved to {output_file}")

        except Exception as e:
            logger.error(f"Error saving JSON snapshot: {e}")
            raise

    def generate_csv_report(self, output_file: str, limit: int = 100):
        """
        Generate CSV report from metrics log.

        Args:
            output_file: Output CSV file path
            limit: Maximum number of records to include (0 = all)
        """
        try:
            if not self.metrics_log_path.exists():
                raise FileNotFoundError(f"Metrics log not found: {self.metrics_log_path}")

            # Read metrics from log
            metrics_list = []

            with open(self.metrics_log_path, 'r') as f:
                lines = f.readlines()

            # Apply limit if specified
            if limit > 0 and len(lines) > limit:
                lines = lines[-limit:]

            # Parse JSONL
            for line in lines:
                try:
                    metrics = json.loads(line.strip())
                    metrics_list.append(metrics)
                except json.JSONDecodeError:
                    continue

            if not metrics_list:
                raise ValueError("No valid metrics found in log file")

            # Flatten metrics for CSV
            flattened = []
            for metrics in metrics_list:
                row = self._flatten_metrics(metrics)
                flattened.append(row)

            # Write CSV
            if flattened:
                fieldnames = sorted(flattened[0].keys())

                with open(output_file, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(flattened)

                logger.info(f"CSV report saved to {output_file} ({len(flattened)} records)")
            else:
                raise ValueError("No data to write to CSV")

        except Exception as e:
            logger.error(f"Error generating CSV report: {e}")
            raise

    def _flatten_metrics(self, metrics: Dict[str, Any], prefix: str = '') -> Dict[str, Any]:
        """Flatten nested metrics dictionary for CSV export."""
        flat = {}

        for key, value in metrics.items():
            new_key = f"{prefix}{key}" if prefix else key

            if isinstance(value, dict):
                # Recursively flatten nested dicts
                flat.update(self._flatten_metrics(value, f"{new_key}_"))
            elif isinstance(value, list):
                # Handle lists by converting to string or extracting key metrics
                if key == 'partitions':
                    # For disk partitions, create separate columns per partition
                    for i, partition in enumerate(value):
                        if isinstance(partition, dict):
                            for pk, pv in partition.items():
                                flat[f"{new_key}_{i}_{pk}"] = pv
                elif key == 'interfaces':
                    # For network interfaces, create separate columns per interface
                    for i, interface in enumerate(value):
                        if isinstance(interface, dict):
                            for ik, iv in interface.items():
                                flat[f"{new_key}_{i}_{ik}"] = iv
                elif key == 'top_processes':
                    # For top processes, include top 3
                    for i, proc in enumerate(value[:3]):
                        if isinstance(proc, dict):
                            for pk, pv in proc.items():
                                flat[f"{new_key}_{i}_{pk}"] = pv
                else:
                    # Convert other lists to comma-separated strings
                    flat[new_key] = ', '.join(str(v) for v in value)
            else:
                # Simple value
                flat[new_key] = value

        return flat

    def get_metrics_summary(self, limit: int = 100) -> Dict[str, Any]:
        """
        Get summary statistics from metrics log.

        Args:
            limit: Number of recent records to analyze

        Returns:
            Dictionary with summary statistics
        """
        try:
            if not self.metrics_log_path.exists():
                return {}

            metrics_list = []

            with open(self.metrics_log_path, 'r') as f:
                lines = f.readlines()

            # Apply limit
            if limit > 0 and len(lines) > limit:
                lines = lines[-limit:]

            # Parse metrics
            for line in lines:
                try:
                    metrics = json.loads(line.strip())
                    metrics_list.append(metrics)
                except json.JSONDecodeError:
                    continue

            if not metrics_list:
                return {}

            # Calculate statistics
            cpu_values = [m.get('cpu', {}).get('percent_total', 0) for m in metrics_list]
            memory_values = [m.get('memory', {}).get('percent', 0) for m in metrics_list]

            summary = {
                'total_records': len(metrics_list),
                'time_range': {
                    'start': metrics_list[0].get('timestamp', 'unknown'),
                    'end': metrics_list[-1].get('timestamp', 'unknown')
                },
                'cpu': {
                    'avg': sum(cpu_values) / len(cpu_values) if cpu_values else 0,
                    'min': min(cpu_values) if cpu_values else 0,
                    'max': max(cpu_values) if cpu_values else 0
                },
                'memory': {
                    'avg': sum(memory_values) / len(memory_values) if memory_values else 0,
                    'min': min(memory_values) if memory_values else 0,
                    'max': max(memory_values) if memory_values else 0
                }
            }

            return summary

        except Exception as e:
            logger.error(f"Error generating metrics summary: {e}")
            return {}

    def get_recent_metrics(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Read recent metrics from log file."""
        try:
            if not self.metrics_log_path.exists():
                return []

            metrics_list = []

            with open(self.metrics_log_path, 'r') as f:
                lines = f.readlines()

            # Get last N lines
            for line in lines[-limit:]:
                try:
                    metrics = json.loads(line.strip())
                    metrics_list.append(metrics)
                except json.JSONDecodeError:
                    continue

            return list(reversed(metrics_list))  # Most recent first

        except Exception as e:
            logger.error(f"Error reading recent metrics: {e}")
            return []

    def clear_metrics_log(self):
        """Clear the metrics log file (use with caution)."""
        try:
            if self.metrics_log_path.exists():
                self.metrics_log_path.unlink()
                logger.info(f"Metrics log cleared: {self.metrics_log_path}")
            else:
                logger.warning(f"Metrics log does not exist: {self.metrics_log_path}")

        except Exception as e:
            logger.error(f"Error clearing metrics log: {e}")
            raise

    def rotate_logs(self, max_lines: int = 10000):
        """
        Rotate metrics log file if it exceeds max_lines.

        Args:
            max_lines: Maximum number of lines before rotation
        """
        try:
            if not self.metrics_log_path.exists():
                return

            # Count lines
            with open(self.metrics_log_path, 'r') as f:
                line_count = sum(1 for _ in f)

            if line_count <= max_lines:
                return

            # Rotate: keep last max_lines
            with open(self.metrics_log_path, 'r') as f:
                lines = f.readlines()

            # Keep only the last max_lines
            with open(self.metrics_log_path, 'w') as f:
                f.writelines(lines[-max_lines:])

            logger.info(f"Metrics log rotated: kept last {max_lines} lines")

        except Exception as e:
            logger.error(f"Error rotating metrics log: {e}")
