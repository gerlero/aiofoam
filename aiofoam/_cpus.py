from __future__ import annotations

import asyncio
import multiprocessing

from contextlib import asynccontextmanager
from typing import AsyncGenerator

max_cpus: int = multiprocessing.cpu_count()
"""
Maximum number of CPUs to use for running cases. Defaults to the number of CPUs on the system.
"""

_reserved_cpus: int = 0
_cpus_cond = None  # Cannot be initialized here yet


@asynccontextmanager
async def exclusive_cpus(cpus: int) -> AsyncGenerator[None, None]:
    global _reserved_cpus, _cpus_cond
    if _cpus_cond is None:
        _cpus_cond = asyncio.Condition()

    cpus = min(cpus, max_cpus)
    if cpus > 0:
        async with _cpus_cond:
            await _cpus_cond.wait_for(lambda: max_cpus - _reserved_cpus >= cpus)
            _reserved_cpus += cpus
    try:
        yield
    finally:
        if cpus > 0:
            async with _cpus_cond:
                _reserved_cpus -= cpus
                _cpus_cond.notify(cpus)
