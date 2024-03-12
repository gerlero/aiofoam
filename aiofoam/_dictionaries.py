from pathlib import Path
from typing import Any, Union, Sequence, Iterator, Optional, Mapping, MutableMapping

try:
    from PyFoam.RunDictionary.ParsedParameterFile import ParsedParameterFile  # type: ignore
except ModuleNotFoundError:
    pass

from ._subprocess import run_process_sync, CalledProcessError


class Dictionary(MutableMapping[str, Union[str, int, float, "Dictionary"]]):
    """An OpenFOAM dictionary."""

    def __init__(self, _file: "FoamFile", _keywords: Sequence[str]) -> None:
        self._file = _file
        self._keywords = _keywords

    def _foam_dictionary(
        self, args: Sequence[str], *, key: Optional[str] = None
    ) -> str:
        keywords = self._keywords

        if key is not None:
            keywords = [*self._keywords, key]

        if keywords:
            args = ["-entry", "/".join(keywords), *args]

        return (
            run_process_sync(
                ["foamDictionary", *args, "-precision", "15", self._file.path],
            )
            .stdout.decode()
            .strip()
        )

    @staticmethod
    def _str(d: Any) -> str:
        if isinstance(d, Mapping) and not isinstance(d, Dictionary):
            out = "{ "
            for k, v in d.items():
                out += f"{k} {v}"
                if not isinstance(v, Mapping):
                    out += "; "
            out += "} "
            return out
        else:
            return str(d)

    def __getitem__(self, key: str) -> Union[str, int, float, "Dictionary"]:
        try:
            ret = self._foam_dictionary(["-value"], key=key)
        except CalledProcessError as e:
            if "Cannot find entry" in e.stderr.decode():
                raise KeyError(key) from e
            else:
                raise

        if ret.startswith("{"):
            return Dictionary(self._file, [*self._keywords, key])

        try:
            return int(ret)
        except ValueError:
            pass

        try:
            return float(ret)
        except ValueError:
            pass

        return ret

    def __setitem__(self, key: str, value: Any) -> None:
        self._foam_dictionary(["-set", self._str(value)], key=key)

    def __delitem__(self, key: str) -> None:
        self._foam_dictionary(["-remove"], key=key)

    def __iter__(self) -> Iterator[str]:
        for key in self._foam_dictionary(["-keywords"]).splitlines():
            if not key.startswith('"'):
                yield key

    def __len__(self) -> int:
        return len(list(iter(self)))

    def __str__(self) -> str:
        return self._foam_dictionary(["-value"])


class FoamFile(Dictionary):
    """An OpenFOAM dictionary file."""

    def __init__(self, path: Union[str, Path]) -> None:
        super().__init__(self, [])
        self.path = Path(path).absolute()
        if self.path.is_dir():
            raise IsADirectoryError(self.path)
        elif not self.path.is_file():
            raise FileNotFoundError(self.path)

    def to_pyfoam(self) -> "ParsedParameterFile":
        """
        Create a PyFoam `ParsedParameterFile` from this case. Requires `PyFoam` to be installed.
        """
        from PyFoam.RunDictionary.ParsedParameterFile import ParsedParameterFile

        return ParsedParameterFile(self.path)

    def __fspath__(self) -> str:
        return str(self.path)
