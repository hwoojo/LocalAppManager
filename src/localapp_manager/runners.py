"""Safe argv-based application execution."""

from __future__ import annotations

from collections.abc import Sequence
import os
from pathlib import Path
import subprocess

from .errors import LocalAppError
from .models import AppManifest


class RunError(LocalAppError):
    pass


def validate_runnable(manifest: AppManifest) -> None:
    executable = Path(manifest.command[0])
    if not executable.exists():
        raise RunError(f"executable does not exist: {executable}")
    if not executable.is_file():
        raise RunError(f"executable is not a regular file: {executable}")
    if not os.access(executable, os.X_OK):
        raise RunError(f"executable is not executable: {executable}")
    if manifest.working_directory is not None:
        working_directory = Path(manifest.working_directory)
        if not working_directory.is_dir():
            raise RunError(f"working directory is unavailable: {working_directory}")


def run_app(manifest: AppManifest, extra_arguments: Sequence[str] = ()) -> int:
    """Run an application without a shell and return its process exit code."""

    validate_runnable(manifest)
    argv = [*manifest.command, *extra_arguments]
    try:
        completed = subprocess.run(
            argv,
            cwd=manifest.working_directory,
            check=False,
            shell=False,
        )
    except OSError as exc:
        raise RunError(f"could not run {manifest.app_id}: {exc}") from exc
    return completed.returncode


def launch_app(manifest: AppManifest, extra_arguments: Sequence[str] = ()) -> int:
    """Launch without blocking a graphical caller and return the child PID."""

    validate_runnable(manifest)
    try:
        process = subprocess.Popen(
            [*manifest.command, *extra_arguments],
            cwd=manifest.working_directory,
            shell=False,
            start_new_session=True,
        )
    except OSError as exc:
        raise RunError(f"could not launch {manifest.app_id}: {exc}") from exc
    return process.pid
