import pytest
import pytest_asyncio

import os
from pathlib import Path
from typing import Optional, Union

from aiofoam import Case

FLANGE = Case(Path(os.environ["FOAM_TUTORIALS"]) / "basic" / "laplacianFoam" / "flange")


@pytest_asyncio.fixture
async def flange(tmp_path: Path) -> Case:
    return await FLANGE.copy(tmp_path / FLANGE.name)


@pytest.mark.asyncio
@pytest.mark.parametrize("parallel", [True, False])
@pytest.mark.parametrize("script", [None, True])
async def test_run(flange: Case, parallel: bool, script: Optional[bool]) -> None:
    await flange.run(parallel=parallel, script=script)
    await flange.clean(script=script)
    await flange.run(parallel=parallel, script=script)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "run_script", ["Allrun", "Allrun-parallel", Path("Allrun"), Path("Allrun-parallel")]
)
@pytest.mark.parametrize("clean_script", ["Allclean", Path("Allclean")])
async def test_run_scripts(
    flange: Case,
    run_script: Union[Path, str],
    clean_script: Union[Path, str],
) -> None:
    await flange.run(script=run_script)
    await flange.clean(script=clean_script)
    await flange.run(script=run_script)


@pytest.mark.asyncio
@pytest.mark.parametrize("script", [None, True])
async def test_run_no_parallel(
    flange: Case, script: Union[None, bool, Path, str]
) -> None:
    with pytest.raises(RuntimeError):
        await flange.run(script=script)


def test_path() -> None:
    assert Path(FLANGE) == FLANGE.path
