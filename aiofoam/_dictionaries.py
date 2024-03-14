from pathlib import Path
from typing import Any, Union, Sequence, Iterator, Optional, Mapping, MutableMapping
from contextlib import suppress

try:
    from PyFoam.RunDictionary.ParsedParameterFile import ParsedParameterFile  # type: ignore
except ModuleNotFoundError:
    pass

from ._subprocess import run_process_sync, CalledProcessError


class Dictionary(MutableMapping[str, Union["Dictionary._Entry", "Dictionary"]]):

    _Entry = Union[str, int, float, bool, Sequence["_Entry"]]
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
    def _parse_entry(entry: str) -> "Dictionary._Entry":
        if entry == "yes":
            return True
        elif entry == "no":
            return False

        with suppress(ValueError):
            return int(entry)

        with suppress(ValueError):
            return float(entry)

        start = entry.find("(")
        if start != -1:
            assert entry.endswith(")")
            elems = []
            nested = 0
            start += 2
            for i, c in enumerate(entry[start:-1], start=start):
                if c == "(":
                    nested += 1
                elif c == ")":
                    nested -= 1
                elif c == " " and nested == 0:
                    elems.append(entry[start:i])
                    start = i + 1

            return [Dictionary._parse_entry(e) for e in elems]

        return entry

    @staticmethod
    def _str(d: Any) -> str:
        if isinstance(d, bool):
            return "yes" if d else "no"

        if isinstance(d, Mapping) and not isinstance(d, Dictionary):
            out = "{ "
            for k, v in d.items():
                out += f"{k} {Dictionary._str(v)}"
                if not isinstance(v, Mapping):
                    out += "; "
            out += "} "
            return out
        elif isinstance(d, Sequence) and not isinstance(d, str):
            out = "( "
            for v in d:
                out += f"{Dictionary._str(v)} "
            out += ") "
            return out
        else:
            return str(d)

    def __getitem__(self, key: str) -> Union[_Entry, "Dictionary"]:
        try:
            ret = self._foam_dictionary(["-value"], key=key)
        except CalledProcessError as e:
            if "Cannot find entry" in e.stderr.decode():
                raise KeyError(key) from e
            else:
                raise

        if ret.startswith("{"):
            assert ret.endswith("}")
            return Dictionary(self._file, [*self._keywords, key])

        return Dictionary._parse_entry(ret)

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

    @property
    def internal_field(self) -> Union[Dictionary._Entry, Dictionary]:
        return self["internalField"]

    @property
    def boundary_field(self) -> Union[Dictionary._Entry, Dictionary]:
        return self["boundaryField"]

    def to_pyfoam(self) -> "ParsedParameterFile":
        """
        Create a PyFoam `ParsedParameterFile` from this case. Requires `PyFoam` to be installed.
        """
        from PyFoam.RunDictionary.ParsedParameterFile import ParsedParameterFile

        return ParsedParameterFile(self.path)

    def __fspath__(self) -> str:
        return str(self.path)
