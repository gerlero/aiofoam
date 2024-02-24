import pytest

import os
from pathlib import Path
from typing import Optional

from aiofoam import Case

PITZ = Case(
    Path(os.environ["FOAM_TUTORIALS"]) / "incompressible" / "simpleFoam" / "pitzDaily"
)


@pytest.fixture
async def pitz(tmp_path: Path) -> Case:
    return await PITZ.copy(tmp_path / PITZ.name)


@pytest.mark.asyncio_cooperative
@pytest.mark.parametrize("script", [None, False])
async def test_run(pitz: Case, script: Optional[bool]) -> None:
    await pitz.run(script=script)
    await pitz.clean(script=script)
    await pitz.run(script=script)


@pytest.mark.asyncio_cooperative
async def test_double_clean(pitz: Case) -> None:
    await pitz.clean()
    await pitz.clean(check=True)
    await pitz.run()


@pytest.mark.asyncio_cooperative
async def test_run_script(pitz: Case) -> None:
    with pytest.raises(RuntimeError):
        await pitz.run(script=True)


@pytest.mark.asyncio_cooperative
@pytest.mark.parametrize("script", [None, False])
async def test_run_parallel(pitz: Case, script: Optional[bool]) -> None:
    with pytest.raises(RuntimeError):
        await pitz.run(script=script, parallel=True)
