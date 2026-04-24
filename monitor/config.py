"""
Configuration management with Pydantic validation.
"""

from pathlib import Path
from typing import List
from pydantic import BaseModel, field_validator
import yaml


class ThresholdConfig(BaseModel):
    """System metric thresholds for alerting."""
    cpu_percent: float = 85.0
    memory_percent: float = 85.0
    disk_percent: float = 90.0
    swap_percent: float = 80.0

    @field_validator('cpu_percent', 'memory_percent', 'disk_percent', 'swap_percent')
    @classmethod
    def validate_percentage(cls, v: float) -> float:
        if not 0 <= v <= 100:
            raise ValueError(f"Percentage must be between 0 and 100, got {v}")
        return v


class SMTPConfig(BaseModel):
    """SMTP email configuration for alerts."""
    enabled: bool = False
    host: str = "smtp.gmail.com"
    port: int = 587
    username: str = ""
    password: str = ""
    from_addr: str = "admin@example.com"
    to_addrs: List[str] = ["alerts@example.com"]
    use_tls: bool = True

    @field_validator('username', 'password', 'from_addr', 'host', mode='before')
    @classmethod
    def coerce_none_to_str(cls, v):
        """YAML parses blank values as None — convert to empty string."""
        return v if v is not None else ""

    @field_validator('to_addrs', mode='before')
    @classmethod
    def coerce_none_addrs(cls, v):
        """Handle None items in the to_addrs list."""
        if v is None:
            return ["alerts@example.com"]
        if isinstance(v, list):
            return [addr for addr in v if addr is not None] or ["alerts@example.com"]
        return v

    @field_validator('port')
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {v}")
        return v


class AlertConfig(BaseModel):
    """Alert system configuration."""
    enabled: bool = True
    cooldown_minutes: int = 5
    log_file: str = "alerts.jsonl"

    @field_validator('cooldown_minutes')
    @classmethod
    def validate_cooldown(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"Cooldown must be non-negative, got {v}")
        return v


class MonitorConfig(BaseModel):
    """Main configuration for the health monitor."""
    thresholds: ThresholdConfig = ThresholdConfig()
    smtp: SMTPConfig = SMTPConfig()
    alerts: AlertConfig = AlertConfig()
    collection_interval: int = 5
    metrics_log: str = "metrics.jsonl"

    @field_validator('collection_interval')
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"Collection interval must be at least 1 second, got {v}")
        return v

    @classmethod
    def load(cls, path: Path | str) -> "MonitorConfig":
        """Load configuration from YAML file."""
        config_path = Path(path)

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)

        return cls(**data)

    def save(self, path: Path | str):
        """Save configuration to YAML file."""
        config_path = Path(path)

        with open(config_path, 'w') as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False, indent=2)

    def get_nested(self, key: str):
        """Get nested configuration value using dot notation (e.g., 'thresholds.cpu_percent')."""
        parts = key.split('.')
        value = self

        for part in parts:
            if hasattr(value, part):
                value = getattr(value, part)
            else:
                raise KeyError(f"Configuration key not found: {key}")

        return value

    def set_nested(self, key: str, value: str):
        """Set nested configuration value using dot notation."""
        parts = key.split('.')

        if len(parts) < 2:
            raise ValueError(f"Key must be nested (e.g., 'thresholds.cpu_percent'), got: {key}")

        obj = self
        for part in parts[:-1]:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                raise KeyError(f"Configuration key not found: {'.'.join(parts[:-1])}")

        field_name = parts[-1]
        if not hasattr(obj, field_name):
            raise KeyError(f"Configuration key not found: {key}")

        # Get field type and convert value
        field_type = type(getattr(obj, field_name))

        if field_type == bool:
            converted_value = value.lower() in ('true', '1', 'yes', 'on')
        elif field_type == int:
            converted_value = int(value)
        elif field_type == float:
            converted_value = float(value)
        else:
            converted_value = value

        setattr(obj, field_name, converted_value)
