import pytest

from aiofoam import Case


@pytest.mark.asyncio_cooperative
def test_invalid_case() -> None:
    with pytest.raises(NotADirectoryError):
        Case("invalid_case")
