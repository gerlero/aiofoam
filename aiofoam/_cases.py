import os

from pathlib import Path
from typing import Optional, Union, Collection, Mapping, Set, Sequence

import aioshutil

try:
    from PyFoam.RunDictionary.SolutionDirectory import SolutionDirectory  # type: ignore
except ModuleNotFoundError:
    pass

from ._subprocess import run_process, CalledProcessError
from ._cpus import exclusive_cpus
from ._dictionaries import FoamFile


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

    @property
    def _application(self) -> str:
        """
        Return the application name as set in the controlDict.
        """
        application = self.control_dict["application"]
        assert isinstance(application, str)
        return application

    @property
    def _nsubdomains(self) -> Optional[int]:
        """
        Return the number of subdomains as set in the decomposeParDict, or None if no decomposeParDict is found.
        """
        try:
            nsubdomains = self.decompose_par_dict["numberOfSubdomains"]
            assert isinstance(nsubdomains, int)
            return nsubdomains
        except FileNotFoundError:
            return None

    @property
    def _nprocessors(self) -> int:
        """
        Return the number of processor directories in the case.
        """
        return len(list(self.path.glob("processor*")))

    async def cmd(
        self,
        args: Union[Sequence[Union[str, Path]], str, Path],
        *,
        parallel: bool = False,
        check: bool = True,
        cpus: int = 0,
        env: Optional[Mapping[str, str]] = None,
    ) -> str:
        """
        Execute a command in the context of this case.

        :param args: The command to execute. If a sequence, the first element is the command and the rest are arguments. If a string, the command is executed in a shell.
        :param parallel: If True, run the command in parallel using `mpiexec`.
        :param check: If True, raise a `RuntimeError` if the command returns a non-zero exit code.
        :param cpus: The number of CPUs to reserve for the command. The command will wait until the requested number of CPUs is available.
        :param env: Environment variables to set for the command. If None, use the current environment.
        """
        if env is None:
            env = os.environ
        env = dict(env)
        if "PWD" in env and Path(env["PWD"]) == Path.cwd():
            env["PWD"] = str(self.path)

        if parallel:
            if isinstance(args, str) or not isinstance(args, Sequence):
                args = f"mpiexec -np {self._nprocessors} {args} -parallel"
            else:
                args = [
                    "mpiexec",
                    "-np",
                    str(self._nprocessors),
                    args[0],
                    "-parallel",
                    *args[1:],
                ]

        try:
            async with exclusive_cpus(cpus):
                proc = await run_process(
                    args,
                    check=check,
                    cwd=self.path,
                    env=env,
                )
        except CalledProcessError as e:
            raise RuntimeError(
                f"{args} failed with return code {e.returncode}\n{e.stderr.decode()}"
            )

        return proc.stdout.decode()

    async def clean(
        self,
        *,
        script: bool = True,
        check: bool = False,
        env: Optional[Mapping[str, str]] = None,
    ) -> None:
        """
        Clean this case.

        :param script: If True, use an (All)clean script if it exists. If False, ignore any clean scripts.
        :param check: If True, raise a `RuntimeError` if the clean script returns a non-zero exit code.
        :param env: Environment variables to set for the clean script. If None, use the current environment.
        """
        script_path = self._clean_script() if script else None

        if script_path is not None:
            await self.cmd([script_path], check=check, env=env)
        else:
            for p in self._clean_paths():
                await aioshutil.rmtree(p)

    async def run(
        self,
        *,
        script: bool = True,
        parallel: Optional[bool] = None,
        cpus: Optional[int] = None,
        check: bool = True,
        env: Optional[Mapping[str, str]] = None,
    ) -> str:
        """
        Run this case.

        :param script: If True, use an (All)run(-parallel) script if it exists. If False, ignore any run scripts.
        :param parallel: If True, run in parallel. If False, run in serial. If None, autodetect whether to run in parallel.
        :param cpus: The number of CPUs to reserve for the run. The run will wait until the requested number of CPUs is available. If None, autodetect the number of CPUs to reserve.
        :param check: If True, raise a `RuntimeError` if any command returns a non-zero exit code.
        :param env: Environment variables to set for the run script or commands. If None, use the current environment.
        """
        script_path = self._run_script(parallel=parallel) if script else None

        if script_path is not None:
            if cpus is None:
                if self._nprocessors > 0:
                    cpus = self._nprocessors
                else:
                    nsubdomains = self._nsubdomains
                    if nsubdomains is not None:
                        cpus = nsubdomains
                    else:
                        cpus = 1

            return await self.cmd([script_path], check=check, cpus=cpus, env=env)

        else:
            if (self.path / "system" / "blockMeshDict").is_file():
                await self.block_mesh()

            if parallel is None:
                parallel = (
                    self._nprocessors > 0
                    or (self.path / "system" / "decomposeParDict").is_file()
                )

            if parallel:
                if (
                    self._nprocessors == 0
                    and (self.path / "system" / "decomposeParDict").is_file()
                ):
                    await self.decompose_par()

                if cpus is None:
                    cpus = min(self._nprocessors, 1)
            else:
                if cpus is None:
                    cpus = 1

            return await self.cmd(
                [self._application],
                parallel=parallel,
                check=check,
                cpus=cpus,
                env=env,
            )

    async def block_mesh(self) -> None:
        """
        Run blockMesh on this case.
        """
        await self.cmd(["blockMesh"])

    async def decompose_par(self) -> None:
        """
        Decompose this case for parallel running.
        """
        await self.cmd(["decomposePar"])

    async def reconstruct_par(self) -> None:
        """
        Reconstruct this case after parallel running.
        """
        await self.cmd(["reconstructPar"])

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

        def ignore(path: Union[Path, str], names: Collection[str]) -> Collection[str]:
            paths = {Path(path) / name for name in names}
            return {p.name for p in paths.intersection(clean_paths)}

        await aioshutil.copytree(self.path, dest, symlinks=True, ignore=ignore)

        return Case(dest)

    @property
    def name(self) -> str:
        """
        The name of the case.
        """
        return self.path.name

    @property
    def control_dict(self) -> FoamFile:
        """
        The controlDict file.
        """
        return FoamFile(self.path / "system" / "controlDict")

    @property
    def fv_schemes(self) -> FoamFile:
        """
        The fvSchemes file.
        """
        return FoamFile(self.path / "system" / "fvSchemes")

    @property
    def fv_solution(self) -> FoamFile:
        """
        The fvSolution file.
        """
        return FoamFile(self.path / "system" / "fvSolution")

    @property
    def decompose_par_dict(self) -> FoamFile:
        """
        The decomposeParDict file.
        """
        return FoamFile(self.path / "system" / "decomposeParDict")

    @property
    def block_mesh_dict(self) -> FoamFile:
        """
        The blockMeshDict file.
        """
        return FoamFile(self.path / "system" / "blockMeshDict")

    @property
    def transport_properties(self) -> FoamFile:
        """
        The transportProperties file.
        """
        return FoamFile(self.path / "constant" / "transportProperties")

    @property
    def turbulence_properties(self) -> FoamFile:
        """
        The turbulenceProperties file.
        """
        return FoamFile(self.path / "constant" / "turbulenceProperties")

    def to_pyfoam(self) -> "SolutionDirectory":
        """
        Create a PyFoam `SolutionDirectory` from this case. Requires `PyFoam` to be installed.
        """
        from PyFoam.RunDictionary.SolutionDirectory import SolutionDirectory

        return SolutionDirectory(self.path)

    def __fspath__(self) -> str:
        return str(self.path)

    def __repr__(self) -> str:
        return f"Case({self.path!r})"

    def __str__(self) -> str:
        return str(self.path)
