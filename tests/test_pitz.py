import pytest
import pytest_asyncio

import os
from pathlib import Path
from typing import Optional, Union

from aiofoam import Case

PITZ = Case(
    Path(os.environ["FOAM_TUTORIALS"]) / "incompressible" / "simpleFoam" / "pitzDaily"
)


@pytest_asyncio.fixture
async def pitz(tmp_path: Path) -> Case:
    return await PITZ.clone(tmp_path / PITZ.name)


@pytest.mark.asyncio
async def test_run(pitz: Case) -> None:
    await pitz.run()
    await pitz.clean()
    await pitz.run()


@pytest.mark.asyncio
async def test_double_clean(pitz: Case) -> None:
    await pitz.clean()
    await pitz.clean(check=True)
    await pitz.run()


@pytest.mark.asyncio
async def test_run_parallel(pitz: Case) -> None:
    with pytest.raises(RuntimeError):
        await pitz.run(parallel=True)


@pytest.mark.asyncio
async def test_pyfoam(pitz: Case) -> None:
    pytest.importorskip("PyFoam")

    assert pitz.to_pyfoam().times == ["0"]
