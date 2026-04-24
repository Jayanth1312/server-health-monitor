"""
System metrics collection using psutil.
"""

import socket
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any
import psutil
from loguru import logger


@dataclass
class CPUMetrics:
    """CPU usage metrics."""
    percent_total: float
    percent_per_core: List[float]
    load_average: List[float]  # 1min, 5min, 15min
    top_processes: List[Dict[str, Any]]  # [{pid, name, cpu_percent}]


@dataclass
class MemoryMetrics:
    """Memory and swap usage metrics."""
    total: int
    available: int
    percent: float
    used: int
    free: int
    cached: int
    swap_total: int
    swap_used: int
    swap_percent: float


@dataclass
class DiskMetrics:
    """Disk usage and I/O metrics."""
    partitions: List[Dict[str, Any]]  # [{device, mountpoint, fstype, total, used, percent}]
    io_counters: Dict[str, Any]  # {read_bytes, write_bytes, read_count, write_count}


@dataclass
class NetworkMetrics:
    """Network interface and connection metrics."""
    interfaces: List[Dict[str, Any]]  # [{name, bytes_sent, bytes_recv, ...}]
    connections: int
    listening_ports: List[int]


class SystemCollector:
    """Collects system metrics using psutil."""

    def __init__(self):
        """Initialize the collector."""
        self.hostname = socket.gethostname()

    def collect_cpu(self) -> CPUMetrics:
        """Collect CPU metrics."""
        try:
            # Get overall CPU percentage (non-blocking)
            cpu_percent = psutil.cpu_percent(interval=1)

            # Get per-core percentages
            per_core = psutil.cpu_percent(interval=0.1, percpu=True)

            # Get load average (Unix only)
            try:
                load_avg = list(psutil.getloadavg())
            except (AttributeError, OSError):
                load_avg = [0.0, 0.0, 0.0]

            # Get top 5 CPU-consuming processes
            top_procs = self.get_top_processes(n=5, sort_by='cpu')

            return CPUMetrics(
                percent_total=cpu_percent,
                percent_per_core=per_core,
                load_average=load_avg,
                top_processes=top_procs
            )

        except Exception as e:
            logger.error(f"Error collecting CPU metrics: {e}")
            return CPUMetrics(
                percent_total=0.0,
                percent_per_core=[],
                load_average=[0.0, 0.0, 0.0],
                top_processes=[]
            )

    def collect_memory(self) -> MemoryMetrics:
        """Collect memory and swap metrics."""
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            return MemoryMetrics(
                total=mem.total,
                available=mem.available,
                percent=mem.percent,
                used=mem.used,
                free=mem.free,
                cached=getattr(mem, 'cached', 0),
                swap_total=swap.total,
                swap_used=swap.used,
                swap_percent=swap.percent
            )

        except Exception as e:
            logger.error(f"Error collecting memory metrics: {e}")
            return MemoryMetrics(
                total=0, available=0, percent=0.0, used=0, free=0,
                cached=0, swap_total=0, swap_used=0, swap_percent=0.0
            )

    def collect_disk(self) -> DiskMetrics:
        """Collect disk usage and I/O metrics."""
        try:
            partitions = []

            for partition in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    partitions.append({
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'fstype': partition.fstype,
                        'total': usage.total,
                        'used': usage.used,
                        'free': usage.free,
                        'percent': usage.percent
                    })
                except (PermissionError, OSError) as e:
                    logger.debug(f"Cannot access {partition.mountpoint}: {e}")
                    continue

            # Get disk I/O counters
            try:
                io = psutil.disk_io_counters()
                io_counters = {
                    'read_bytes': io.read_bytes,
                    'write_bytes': io.write_bytes,
                    'read_count': io.read_count,
                    'write_count': io.write_count
                } if io else {}
            except Exception as e:
                logger.debug(f"Cannot get disk I/O counters: {e}")
                io_counters = {}

            return DiskMetrics(
                partitions=partitions,
                io_counters=io_counters
            )

        except Exception as e:
            logger.error(f"Error collecting disk metrics: {e}")
            return DiskMetrics(partitions=[], io_counters={})

    def collect_network(self) -> NetworkMetrics:
        """Collect network interface and connection metrics."""
        try:
            interfaces = []

            # Get network interface stats
            net_io = psutil.net_io_counters(pernic=True)

            for interface, stats in net_io.items():
                interfaces.append({
                    'name': interface,
                    'bytes_sent': stats.bytes_sent,
                    'bytes_recv': stats.bytes_recv,
                    'packets_sent': stats.packets_sent,
                    'packets_recv': stats.packets_recv,
                    'errin': stats.errin,
                    'errout': stats.errout,
                    'dropin': stats.dropin,
                    'dropout': stats.dropout
                })

            # Count established connections
            try:
                connections = [c for c in psutil.net_connections()
                             if c.status == 'ESTABLISHED']
                conn_count = len(connections)
            except (PermissionError, psutil.AccessDenied):
                logger.debug("Cannot access network connections (needs elevated privileges)")
                conn_count = 0

            # Get listening ports
            listening_ports = self._get_listening_ports()

            return NetworkMetrics(
                interfaces=interfaces,
                connections=conn_count,
                listening_ports=listening_ports
            )

        except Exception as e:
            logger.error(f"Error collecting network metrics: {e}")
            return NetworkMetrics(interfaces=[], connections=0, listening_ports=[])

    def _get_listening_ports(self) -> List[int]:
        """Get list of listening ports."""
        try:
            listening = []
            for conn in psutil.net_connections(kind='inet'):
                if conn.status == 'LISTEN' and conn.laddr:
                    listening.append(conn.laddr.port)
            return sorted(set(listening))
        except (PermissionError, psutil.AccessDenied):
            logger.debug("Cannot access listening ports (needs elevated privileges)")
            return []
        except Exception as e:
            logger.debug(f"Error getting listening ports: {e}")
            return []

    def collect_all(self) -> Dict[str, Any]:
        """Collect all metrics and return as dictionary with timestamp."""
        cpu = self.collect_cpu()
        memory = self.collect_memory()
        disk = self.collect_disk()
        network = self.collect_network()

        return {
            'timestamp': datetime.now().isoformat(),
            'hostname': self.hostname,
            'cpu': asdict(cpu),
            'memory': asdict(memory),
            'disk': asdict(disk),
            'network': asdict(network)
        }

    def get_process_info(self, pid: int) -> Dict[str, Any]:
        """Get detailed information about a specific process."""
        try:
            proc = psutil.Process(pid)
            with proc.oneshot():
                return {
                    'pid': proc.pid,
                    'name': proc.name(),
                    'status': proc.status(),
                    'cpu_percent': proc.cpu_percent(interval=0.1),
                    'memory_percent': proc.memory_percent(),
                    'memory_info': proc.memory_info()._asdict(),
                    'create_time': datetime.fromtimestamp(proc.create_time()).isoformat(),
                    'username': proc.username(),
                    'cmdline': ' '.join(proc.cmdline())
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            logger.debug(f"Cannot access process {pid}: {e}")
            return {}

    def get_top_processes(self, n: int = 5, sort_by: str = 'cpu') -> List[Dict[str, Any]]:
        """Get top N processes sorted by CPU or memory usage."""
        try:
            processes = []

            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    pinfo = proc.info
                    # Get CPU percent with small interval
                    pinfo['cpu_percent'] = proc.cpu_percent(interval=0.1)
                    processes.append(pinfo)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            # Sort by metric
            key = 'cpu_percent' if sort_by == 'cpu' else 'memory_percent'
            processes.sort(key=lambda x: x.get(key, 0), reverse=True)

            return processes[:n]

        except Exception as e:
            logger.error(f"Error getting top processes: {e}")
            return []

    def get_system_uptime(self) -> float:
        """Get system uptime in seconds."""
        try:
            boot_time = psutil.boot_time()
            return datetime.now().timestamp() - boot_time
        except Exception as e:
            logger.error(f"Error getting uptime: {e}")
            return 0.0

    def get_users(self) -> List[Dict[str, Any]]:
        """Get list of logged-in users."""
        try:
            users = []
            for user in psutil.users():
                users.append({
                    'name': user.name,
                    'terminal': user.terminal,
                    'host': user.host,
                    'started': datetime.fromtimestamp(user.started).isoformat()
                })
            return users
        except Exception as e:
            logger.error(f"Error getting users: {e}")
            return []
