import asyncio
import sys

from pathlib import Path
from typing import Union, Sequence, Mapping


async def run(
    args: Union[Sequence[Union[str, Path]], str],
    *,
    check: bool = True,
    shell: Union[None, bool, Path, str] = None,
    cwd: Union[None, str, Path] = None,
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
