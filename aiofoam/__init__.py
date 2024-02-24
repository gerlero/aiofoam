import asyncio
import multiprocessing
import os

from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, Union, AsyncGenerator, Mapping, Set

import aioshutil

__version__ = "0.2.0"

max_cpus: int = multiprocessing.cpu_count()
"""
Maximum number of CPUs to use for running cases. Defaults to the number of CPUs on the system.
"""

_reserved_cpus: int = 0
_cpus_cond = None  # Cannot be initialized here yet


@asynccontextmanager
async def _cpus_sem(cpus: int) -> AsyncGenerator[None, None]:
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


class Case:
    """
    An OpenFOAM case.

    :param path: The path to the case directory.
    """

    def __init__(self, path: Union[Path, str]):
        self.path = Path(path).absolute()
        if not self.path.is_dir():
            raise NotADirectoryError(f"{self.path} is not a directory")

    def _clean_paths(self) -> Set[Path]:
        has_decompose = (self.path / "system" / "decomposeParDict").is_file()
        has_blockmesh = (self.path / "system" / "blockMeshDict").is_file()

        paths: Set[Path] = set()

        for p in self.path.iterdir():
            if p.is_dir():
                try:
                    t = float(p.name)
                except ValueError:
                    pass
                else:
                    if t != 0:
                        paths.add(p)

                if has_decompose and p.name.startswith("processor"):
                    paths.add(p)

        if has_blockmesh and (self.path / "constant" / "polyMesh").exists():
            paths.add(self.path / "constant" / "polyMesh")

        return paths

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
            await self._exec(
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
            await self._exec(
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

    async def _exec(
        self,
        cmd: str,
        *args: str,
        parallel: bool = False,
        check: bool = True,
        cpus: int = 0,
        env: Optional[Mapping[str, str]] = None,
    ) -> str:
        """
        Execute a command in the context of this case.
        """
        if env is None:
            env = os.environ
        env = dict(env)
        env["PWD"] = str(self.path.absolute())

        if parallel:
            args = ("-np", str(self._nprocessors()), cmd, "-parallel", *args)
            cmd = "mpiexec"

        async with _cpus_sem(cpus):
            subproc = await asyncio.create_subprocess_exec(
                cmd,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.path,
                env=env,
            )
            stdout, stderr = await subproc.communicate()

        if check and subproc.returncode != 0:
            raise RuntimeError(
                f"{cmd} failed with return code {subproc.returncode}\n{stderr.decode()}"
            )
        return stdout.decode()

    async def clean(
        self,
        *,
        script: Union[None, bool, Path, str] = None,
        check: bool = False,
        env: Optional[Mapping[str, str]] = None,
    ) -> None:
        """
        Clean this case.

        :param script: The path to the `(All)clean` script. If True, find the clean script automatically. If False, ignore any clean scripts. If None, use the a clean script only if it exists.
        :param check: If True, raise a `RuntimeError` if the clean script returns a non-zero exit code.
        :param env: Environment variables to set for the clean script. If None, use the current environment.
        """
        if script is True or script is None:
            script_path = self._clean_script()
            if script and script_path is None:
                raise RuntimeError("No clean script found")
        elif script is False:
            script_path = None
        else:
            script_path = Path(script)
            if not script_path.is_absolute():
                script_path = self.path / script_path

        if script_path is not None:
            await self._exec(str(script_path), check=check, env=env)
        else:
            for p in self._clean_paths():
                await aioshutil.rmtree(p)

    async def run(
        self,
        *cmd: str,
        script: Union[None, bool, Path, str] = None,
        parallel: Optional[bool] = None,
        cpus: Optional[int] = None,
        check: bool = True,
        env: Optional[Mapping[str, str]] = None,
    ) -> str:
        """
        Run this case.

        :param cmd: Command to run, including arguments. If not provided, autodetect the command to run.
        :param script: The path to the `(All)run` script. If True, find the run script automatically. If False, ignore any run scripts. If None, use a run script if it exists.
        :param parallel: If True, run in parallel. If False, run in serial. If None, autodetect whether to run in parallel.
        :param cpus: The number of CPUs to reserve for the run. The run will wait until the requested number of CPUs is available. If None, autodetect the number of CPUs to reserve.
        :param check: If True, raise a `RuntimeError` if any command returns a non-zero exit code.
        :param env: Environment variables to set for the run script or commands. If None, use the current environment.
        """
        if not cmd:
            script_path: Optional[Path]
            if script is not True and script is not False and script is not None:
                script_path = Path(script)
                if not script_path.is_absolute():
                    script_path = self.path / script_path
            elif script is True or script is None:
                script_path = self._run_script(parallel=parallel)
                if script is True and script_path is None:
                    raise RuntimeError("No run script found")
            elif script is False:
                script_path = None

            if script_path is None:
                if (self.path / "system" / "blockMeshDict").is_file():
                    await self._exec("blockMesh", check=check, cpus=1, env=env)

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
                        await self._exec("decomposePar", check=check, cpus=1, env=env)

                    if cpus is None:
                        cpus = self._nprocessors()
                else:
                    if cpus is None:
                        cpus = 1
                return await self._exec(
                    application, parallel=parallel, check=check, cpus=cpus, env=env
                )

            else:
                if cpus is None:
                    if self._nprocessors() > 0:
                        cpus = self._nprocessors()
                    else:
                        nsubdomains = await self._nsubdomains()
                        if nsubdomains is not None:
                            cpus = nsubdomains
                        else:
                            cpus = 1

                return await self._exec(
                    str(script_path), check=check, cpus=cpus, env=env
                )

        else:
            if script is not None:
                raise ValueError("Cannot specify both cmd and script")

            if parallel is None:
                parallel = False

            if cpus is None:
                if parallel:
                    cpus = self._nprocessors()
                else:
                    cpus = 1

            return await self._exec(
                *cmd, parallel=parallel, check=check, cpus=cpus, env=env
            )

    async def copy(self, dest: Union[Path, str]) -> "Case":
        """
        Make a copy of this case.

        :param dest: The destination path.
        """
        return Case(await aioshutil.copytree(self.path, dest, symlinks=True))

    async def clone(self, dest: Union[Path, str]) -> "Case":
        """
        Clone this case (make a clean copy).

        :param dest: The destination path.
        """
        if self._clean_script() is not None:
            copy = await self.copy(dest)
            await copy.clean()
            return copy

        dest = Path(dest)
        clean_paths = self._clean_paths()
        for p in self.path.iterdir():
            if p not in clean_paths:
                await aioshutil.copytree(p, dest / p.name, symlinks=True)

        return Case(dest)

    @property
    def name(self) -> str:
        """
        The name of the case.
        """
        return self.path.name

    def __fspath__(self) -> str:
        return str(self.path)

    def __repr__(self) -> str:
        return f"Case({self.path!r})"

    def __str__(self) -> str:
        return str(self.path)
