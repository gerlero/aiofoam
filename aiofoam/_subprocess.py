import asyncio
import sys

from pathlib import Path
from typing import Union, Sequence, Mapping
import subprocess
from subprocess import CalledProcessError

__all__ = ["run_process", "run_process_sync", "CalledProcessError"]


async def run_process(
    args: Union[Sequence[Union[str, Path]], str, Path],
    *,
    check: bool = True,
    cwd: Union[None, str, Path] = None,
    env: Union[None, Mapping[str, str]] = None,
) -> "subprocess.CompletedProcess[bytes]":
    if isinstance(args, str) or not isinstance(args, Sequence):
        proc = await asyncio.create_subprocess_shell(
            str(args),
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    else:
        if sys.version_info < (3, 8):
            args = (str(arg) for arg in args)
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    stdout, stderr = await proc.communicate()

    assert proc.returncode is not None

    ret = subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)

    if check:
        ret.check_returncode()

    return ret


def run_process_sync(
    args: Union[Sequence[Union[str, Path]], str, Path],
    *,
    check: bool = True,
    cwd: Union[None, str, Path] = None,
    env: Union[None, Mapping[str, str]] = None,
) -> "subprocess.CompletedProcess[bytes]":
    shell = isinstance(args, str) or not isinstance(args, Sequence)

    if sys.version_info < (3, 8):
        if shell:
            args = str(args)
        else:
            args = (str(arg) for arg in args)

    proc = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=shell,
        check=check,
    )

    return proc
