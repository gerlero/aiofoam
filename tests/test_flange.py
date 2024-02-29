import pytest
import pytest_asyncio

import os
from pathlib import Path

from aiofoam import Case

FLANGE = Case(Path(os.environ["FOAM_TUTORIALS"]) / "basic" / "laplacianFoam" / "flange")


@pytest_asyncio.fixture
async def flange(tmp_path: Path) -> Case:
    return await FLANGE.clone(tmp_path / FLANGE.name)


@pytest.mark.asyncio
@pytest.mark.parametrize("parallel", [True, False])
async def test_run(flange: Case, parallel: bool) -> None:
    await flange.run(parallel=parallel)
    await flange.clean()
    await flange.run(parallel=parallel)


@pytest.mark.asyncio
async def test_run_cmd(flange: Case) -> None:
    (flange.path / "0.orig").rename(flange.path / "0")
    await flange.cmd(
        [
            "ansysToFoam",
            Path(os.environ["FOAM_TUTORIALS"])
            / "resources"
            / "geometry"
            / "flange.ans",
            "-scale",
            "0.001",
        ],
    )
    await flange.cmd(["decomposePar"])
    await flange.cmd(["laplacianFoam"], parallel=True, cpus=4)
    await flange.cmd(["reconstructPar"])


@pytest.mark.asyncio
async def test_run_cmd_shell(flange: Case) -> None:
    (flange.path / "0.orig").rename(flange.path / "0")
    await flange.cmd(
        'ansysToFoam "$FOAM_TUTORIALS/resources/geometry/flange.ans" -scale 0.001'
    )
    await flange.cmd("decomposePar")
    await flange.cmd("laplacianFoam", parallel=True, cpus=4)
    await flange.cmd("reconstructPar")


@pytest.mark.asyncio
async def test_run_no_parallel(flange: Case) -> None:
    with pytest.raises(RuntimeError):
        await flange.run()


def test_path() -> None:
    assert Path(FLANGE) == FLANGE.path
