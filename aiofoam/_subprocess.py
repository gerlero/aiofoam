import asyncio
import sys

from pathlib import Path
from typing import Union, Sequence, Mapping
from subprocess import CompletedProcess, CalledProcessError

__all__ = ["run_process", "CalledProcessError"]


async def run_process(
    args: Union[Sequence[Union[str, Path]], str],
    *,
    check: bool = True,
    shell: Union[None, bool, Path, str] = None,
    cwd: Union[None, str, Path] = None,
    env: Union[None, Mapping[str, str]] = None,
) -> "CompletedProcess[bytes]":
    if shell is None:
        shell = isinstance(args, str)

    if shell:
        if not isinstance(args, str):
            args = " ".join(str(arg) for arg in args)

        if shell is True:
            proc = await asyncio.create_subprocess_shell(
                args,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        else:
            if sys.version_info < (3, 8):
                shell = str(shell)
            proc = await asyncio.create_subprocess_exec(
                shell,
                "-c",
                args,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

    else:
        if isinstance(args, str):
            args = [args]

        if sys.version_info < (3, 8):
            args = [str(arg) for arg in args]
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    stdout, stderr = await proc.communicate()

    assert proc.returncode is not None

    ret = CompletedProcess(args, proc.returncode, stdout, stderr)

    if check:
        ret.check_returncode()

    return ret
