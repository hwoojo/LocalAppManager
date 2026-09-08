from pathlib import Path

import pytest

from localapp_manager import fileops


def test_atomic_replace_many_rolls_back_all_files_on_failure(
    tmp_path: Path, monkeypatch
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.write_bytes(b"old first")
    second.write_bytes(b"old second")
    real_replace = fileops.os.replace
    calls = 0

    def fail_once(source, destination):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError("simulated second publish failure")
        return real_replace(source, destination)

    monkeypatch.setattr(fileops.os, "replace", fail_once)
    with pytest.raises(OSError, match="simulated"):
        fileops.atomic_replace_many(
            {first: (b"new first", 0o600), second: (b"new second", 0o600)}
        )
    assert first.read_bytes() == b"old first"
    assert second.read_bytes() == b"old second"
