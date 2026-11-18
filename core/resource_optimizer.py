"""Resource inspection and conservative CPU limits; standard library only."""

from __future__ import annotations

import os
import platform
import resource
from dataclasses import asdict, dataclass
from pathlib import Path

from core.config import EngineConfig, config


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    cpu_count: int
    cpu_threads: int
    memory_total_mb: int | None
    memory_available_mb: int | None
    process_peak_rss_mb: float
    platform: str


def _memory_info() -> tuple[int | None, int | None]:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return None, None
    values: dict[str, int] = {}
    for line in meminfo.read_text(encoding="utf-8").splitlines():
        key, _, rest = line.partition(":")
        parts = rest.strip().split()
        if parts and parts[0].isdigit():
            values[key] = int(parts[0]) // 1024
    return values.get("MemTotal"), values.get("MemAvailable")


def snapshot(settings: EngineConfig = config) -> ResourceSnapshot:
    total, available = _memory_info()
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_mb = usage / (1024 if platform.system() == "Linux" else 1024 * 1024)
    return ResourceSnapshot(
        cpu_count=max(1, os.cpu_count() or 1),
        cpu_threads=settings.max_cpu_threads,
        memory_total_mb=total,
        memory_available_mb=available,
        process_peak_rss_mb=round(rss_mb, 2),
        platform=platform.platform(),
    )


def apply_thread_limits(settings: EngineConfig = config) -> None:
    threads = str(settings.max_cpu_threads)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(name, threads)


def as_dict(settings: EngineConfig = config) -> dict[str, object]:
    return asdict(snapshot(settings))
