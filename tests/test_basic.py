import pytest

from aiofoam import Case


def test_invalid_case() -> None:
    with pytest.raises(NotADirectoryError):
        Case("invalid_case")
