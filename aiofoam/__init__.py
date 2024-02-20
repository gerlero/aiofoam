import asyncio
import multiprocessing

from pathlib import Path
from typing import Optional, Union

import aioshutil

__version__ = "0.1.2"

max_cpus: int = multiprocessing.cpu_count()
"""
Maximum number of CPUs to use for running cases. Defaults to the number of CPUs on the system.
"""

_reserved_cpus = 0
_cpus_cond = asyncio.Condition()


class Case:
    """
    An OpenFOAM case.

    :param path: The path to the case directory.
    """

    def __init__(self, path: Union[Path, str], /):
        self.path = Path(path)

    def _clean_script(self) -> Optional[Path]:
        """
        Return the path to the (All)clean script, or None if no clean script is found.
        """
        clean = self.path / "clean"
        all_clean = self.path / "Allclean"

        if clean.is_file():
            return clean
        elif all_clean.is_file():
            return all_clean
        else:
            return None

    def _run_script(self, *, parallel: Optional[bool]) -> Optional[Path]:
        """
        Return the path to the (All)run script, or None if no run script is found.
        """
        run = self.path / "run"
        run_parallel = self.path / "run-parallel"
        all_run = self.path / "Allrun"
        all_run_parallel = self.path / "Allrun-parallel"

        if run.is_file() or all_run.is_file():
            if run_parallel.is_file() or all_run_parallel.is_file():
                if parallel:
                    return run_parallel if run_parallel.is_file() else all_run_parallel
                elif parallel is False:
                    return run if run.is_file() else all_run
                else:
                    raise RuntimeError(
                        "Both (All)run and (All)run-parallel scripts are present. Please specify parallel argument."
                    )
            return run if run.is_file() else all_run
        elif parallel is not False and (
            run_parallel.is_file() or all_run_parallel.is_file()
        ):
            return run_parallel if run_parallel.is_file() else all_run_parallel
        else:
            return None

    async def _application(self) -> str:
        """
        Return the application name as set in the controlDict.
        """
        return (
            await self.exec(
                "foamDictionary",
                "-entry",
                "application",
                "-value",
                "system/controlDict",
            )
        ).strip()

    async def _nsubdomains(self) -> Optional[int]:
        """
        Return the number of subdomains as set in the decomposeParDict, or None if no decomposeParDict is found.
        """
        if not (self.path / "system" / "decomposeParDict").is_file():
            return None
        return int(
            await self.exec(
                "foamDictionary",
                "-entry",
                "numberOfSubdomains",
                "-value",
                "system/decomposeParDict",
            )
        )

    def _nprocessors(self) -> int:
        """
        Return the number of processor directories in the case.
        """
        return len(list(self.path.glob("processor*")))

    async def exec(
        self, cmd: str, *args: str, check: bool = True, cpus: int = 0
    ) -> str:
        """
        Execute a command inside the case directory.

        :param cmd: The command to execute.
        :param args: Additional arguments for the command.
        :param check: If True, raise a `RuntimeError` if the command returns a non-zero exit code.
        :param cpus: The number of CPUs to reserve for the command. The command will not be executed until the requested number of CPUs is available.
        """
        global _reserved_cpus
        cpus = min(cpus, max_cpus)  # Oversubscribe if necessary
        if cpus > 0:
            async with _cpus_cond:
                await _cpus_cond.wait_for(lambda: max_cpus - _reserved_cpus >= cpus)
                _reserved_cpus += cpus

        subproc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.path,
        )
        stdout, stderr = await subproc.communicate()

        if cpus > 0:
            async with _cpus_cond:
                _reserved_cpus -= cpus
                _cpus_cond.notify(n=cpus)

        if check and subproc.returncode != 0:
            raise RuntimeError(
                f"{cmd} failed with return code {subproc.returncode}\n{stderr.decode()}"
            )
        return stdout.decode()

    async def clean(
        self, script: Union[None, bool, Path, str] = None, *, check: bool = False
    ) -> None:
        """
        Clean this case.

        :param script: The path to the `(All)clean` script. If True, find the clean script automatically. If False, ignore any clean scripts. If None, use the a clean script only if it exists.
        :param check: If True, raise a `RuntimeError` if the clean script returns a non-zero exit code.
        """
        if script is True or script is None:
            script_path = self._clean_script()
            if script and script_path is None:
                raise RuntimeError("No clean script found")
        elif script is False:
            script_path = None
        else:
            script_path = Path(script)

        if script_path is not None:
            await self.exec(str(script_path), check=check)
        else:
            rm_processor = (self.path / "system" / "decomposeParDict").is_file()

            for p in self.path.iterdir():
                if p.is_dir():
                    try:
                        t = float(p.name)
                    except ValueError:
                        pass
                    else:
                        if t != 0:
                            await aioshutil.rmtree(p)
                            continue

                    if rm_processor and p.name.startswith("processor"):
                        await aioshutil.rmtree(p)

            if (self.path / "system" / "blockMeshDict").is_file():
                await aioshutil.rmtree(self.path / "constant" / "polyMesh")

    async def run(
        self,
        script: Union[None, bool, Path, str] = None,
        *,
        parallel: Optional[bool] = None,
        cpus: Optional[int] = None,
        check: bool = True,
    ) -> None:
        """
        Run this case.

        :param script: The path to the `(All)run` script. If True, find the run script automatically. If False, ignore any run scripts. If None, use a run script if it exists.
        :param parallel: If True, run in parallel. If False, run in serial. If None, autodetect whether to run in parallel.
        :param cpus: The number of CPUs to reserve for the run. The run will wait until the requested number of CPUs is available. If None, autodetect the number of CPUs to reserve.
        :param check: If True, raise a `RuntimeError` if any command returns a non-zero exit code.
        """
        if script is True or script is None:
            script_path = self._run_script(parallel=parallel)
            if script and script_path is None:
                raise RuntimeError("No run script found")
        elif script is False:
            script_path = None
        else:
            script_path = Path(script)

        if script_path is not None:
            if cpus is None:
                if self._nprocessors() > 0:
                    cpus = self._nprocessors()
                elif nsubdomains := await self._nsubdomains() is not None:
                    cpus = nsubdomains
                else:
                    cpus = 1

            await self.exec(str(script_path), check=check, cpus=cpus)
        else:
            if (self.path / "system" / "blockMeshDict").is_file():
                await self.exec("blockMesh", check=check)

            if parallel is None:
                if (
                    self._nprocessors() > 0
                    or (self.path / "system" / "decomposeParDict").is_file()
                ):
                    parallel = True
                else:
                    parallel = False

            application = await self._application()
            if parallel:
                if (
                    self._nprocessors() == 0
                    and (self.path / "system" / "decomposeParDict").is_file()
                ):
                    await self.exec("decomposePar", check=check)

                nprocessors = self._nprocessors()
                if cpus is None:
                    cpus = self._nprocessors()

                await self.exec(
                    "mpiexec",
                    "-np",
                    str(nprocessors),
                    application,
                    "-parallel",
                    check=check,
                    cpus=cpus,
                )
            else:
                if cpus is None:
                    cpus = 1
                await self.exec(application, check=check, cpus=cpus)

    def __fspath__(self) -> str:
        return str(self.path)

    def __repr__(self) -> str:
        return f"Case({self.path!r})"

    def __str__(self) -> str:
        return str(self.path)
