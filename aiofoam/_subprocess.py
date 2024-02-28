from __future__ import annotations

import asyncio
import sys
import os

from typing import Union, Sequence, Mapping


async def run(
    args: Union[Sequence[Union[str, os.PathLike[str]]], str],
    *,
    check: bool = True,
    shell: Union[None, bool, os.PathLike[str], str] = None,
    cwd: Union[None, str, os.PathLike[str]] = None,
    env: Union[None, Mapping[str, str]] = None,
) -> str:
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

    if check and proc.returncode != 0:
        raise RuntimeError(
            f"{args} failed with return code {proc.returncode}\n{stderr.decode()}"
        )
    return stdout.decode()
