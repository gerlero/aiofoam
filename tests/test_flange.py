import pytest

import os
import shutil
from pathlib import Path
from typing import Optional

from aiofoam import Case

FLANGE = Case(Path(os.environ["FOAM_TUTORIALS"]) / "basic" / "laplacianFoam" / "flange")


@pytest.fixture
def flange(tmp_path: Path) -> Case:
    dest = tmp_path / FLANGE.path.name
    shutil.copytree(FLANGE.path, dest)
    return Case(dest)


@pytest.mark.asyncio
@pytest.mark.parametrize("parallel", [True, False])
@pytest.mark.parametrize("script", [None, True])
async def test_run(flange: Case, parallel: bool, script: Optional[bool]) -> None:
    await flange.run(parallel=parallel, script=script)
    await flange.clean(script=script)
    await flange.run(parallel=parallel, script=script)


@pytest.mark.asyncio
@pytest.mark.parametrize("script", [None, True])
async def test_run_no_parallel(flange: Case, script: Optional[bool]) -> None:
    with pytest.raises(RuntimeError):
        await flange.run(script=True)


def test_path() -> None:
    assert Path(FLANGE) == FLANGE.path
