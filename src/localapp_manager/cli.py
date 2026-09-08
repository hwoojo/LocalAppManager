"""Command-line interface for registering and running local applications."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys
from typing import TextIO

from . import __version__
from .errors import LocalAppError
from .doctor import diagnose, repair
from .editing import UNSET, edit_app
from .external_sources import discover_gearlever
from .importers import (
    register_external_integration,
    register_file,
    register_portable_folder,
    register_python_project,
)
from .paths import AppPaths
from .removal import build_removal_plan, execute_removal
from .runners import run_app
from .storage import ManifestStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="localapp",
        description="Manage applications installed outside the system package manager.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command_name")

    add_parser = subparsers.add_parser(
        "add", help="register a supported local application"
    )
    add_parser.add_argument(
        "source", help="path to an executable file, portable folder, or Python project"
    )
    add_parser.add_argument("--name", help="display name (defaults to the filename)")
    add_parser.add_argument("--id", dest="app_id", help="explicit application ID")
    add_parser.add_argument(
        "--mode",
        choices=("linked", "managed"),
        default="linked",
        help="keep the source in place or copy it into managed storage",
    )
    add_parser.add_argument(
        "--kind",
        choices=("auto", "appimage", "executable", "portable-folder", "python-project"),
        default="auto",
        help="application kind (default: infer from .AppImage suffix)",
    )
    add_parser.add_argument(
        "--arg",
        dest="app_arguments",
        action="append",
        default=[],
        help="stored application argument; repeat for multiple arguments",
    )
    add_parser.add_argument("--working-directory", help="working directory used when running")
    add_parser.add_argument(
        "--executable",
        help="relative executable path for a portable folder",
    )
    add_parser.add_argument("--python", help="Python interpreter for a Python project")
    python_entry = add_parser.add_mutually_exclusive_group()
    python_entry.add_argument("--script", help="relative Python entry script")
    python_entry.add_argument("--module", help="Python module to run with -m")
    add_parser.add_argument("--icon", help="optional icon file to copy into managed storage")
    add_parser.add_argument(
        "--mime-type", dest="mime_types", action="append", default=[]
    )
    add_parser.add_argument(
        "--desktop-argument", choices=("%f", "%F", "%u", "%U")
    )
    add_parser.add_argument(
        "--category",
        dest="categories",
        action="append",
        default=[],
        help="desktop category; repeat for multiple categories (default: Utility)",
    )
    add_parser.add_argument(
        "--terminal",
        action="store_true",
        help="mark the application as requiring a terminal",
    )
    add_parser.add_argument(
        "--no-startup-notify",
        action="store_false",
        dest="startup_notify",
        help="disable StartupNotify in the desktop entry",
    )

    subparsers.add_parser("list", help="list registered applications")

    show_parser = subparsers.add_parser("show", help="show one manifest as JSON")
    show_parser.add_argument("app_id", help="application ID")

    run_parser = subparsers.add_parser("run", help="run a registered application")
    run_parser.add_argument("app_id", help="application ID")
    run_parser.add_argument(
        "arguments",
        nargs=argparse.REMAINDER,
        help="extra arguments, normally placed after --",
    )
    remove_parser = subparsers.add_parser(
        "remove", help="preview or execute manifest-based removal"
    )
    remove_parser.add_argument("app_id", help="application ID")
    remove_parser.add_argument(
        "--yes",
        action="store_true",
        help="execute the displayed removal plan",
    )
    edit_parser = subparsers.add_parser("edit", help="edit execution and desktop settings")
    edit_parser.add_argument("app_id", help="application ID")
    edit_parser.add_argument("--name", help="new display name")
    argument_group = edit_parser.add_mutually_exclusive_group()
    argument_group.add_argument(
        "--arg", dest="edit_arguments", action="append", default=None,
        help="replace stored arguments; repeat for multiple arguments",
    )
    argument_group.add_argument("--clear-arguments", action="store_true")
    working_group = edit_parser.add_mutually_exclusive_group()
    working_group.add_argument("--working-directory")
    working_group.add_argument("--clear-working-directory", action="store_true")
    edit_parser.add_argument(
        "--terminal", action=argparse.BooleanOptionalAction, default=None
    )
    edit_parser.add_argument(
        "--category", dest="edit_categories", action="append", default=None
    )
    edit_parser.add_argument(
        "--startup-notify", action=argparse.BooleanOptionalAction, default=None
    )
    edit_parser.add_argument(
        "--mime-type", dest="edit_mime_types", action="append", default=None
    )
    edit_parser.add_argument(
        "--desktop-argument", choices=("%f", "%F", "%u", "%U"), default=None
    )

    doctor_parser = subparsers.add_parser("doctor", help="diagnose registered applications")
    doctor_parser.add_argument("app_id", nargs="?", help="optional application ID")
    doctor_parser.add_argument(
        "--repair", action="store_true", help="repair safe integration files and migrate manifests"
    )
    subparsers.add_parser(
        "import-gearlever",
        help="register Gear Lever apps while preserving its desktop integration",
    )
    return parser


def _print_list(store: ManifestStore, stdout: TextIO) -> None:
    manifests = store.list_manifests()
    if not manifests:
        print("No applications registered.", file=stdout)
        return
    print("ID\tNAME\tKIND\tMODE", file=stdout)
    for manifest in manifests:
        print(
            f"{manifest.app_id}\t{manifest.name}\t{manifest.kind.value}\t"
            f"{manifest.install_mode.value}",
            file=stdout,
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = sys.stdout if stdout is None else stdout
    error_output = sys.stderr if stderr is None else stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command_name is None:
        parser.print_help(file=output)
        return 0

    store = ManifestStore(AppPaths.from_environment())
    try:
        if args.command_name == "add":
            source_path = Path(args.source).expanduser()
            portable = args.kind == "portable-folder" or (
                args.kind == "auto" and source_path.is_dir()
            )
            common_options = {
                "mode": args.mode,
                "name": args.name,
                "app_id": args.app_id,
                "arguments": args.app_arguments,
                "working_directory": args.working_directory,
                "terminal": args.terminal,
                "icon": args.icon,
                "categories": args.categories or ("Utility",),
                "startup_notify": args.startup_notify,
                "mime_types": args.mime_types,
                "desktop_argument": args.desktop_argument,
            }
            if args.kind == "python-project":
                if args.python is None:
                    raise ValueError("--python is required for Python projects")
                if args.executable is not None:
                    raise ValueError("--executable is not valid for Python projects")
                manifest = register_python_project(
                    store,
                    args.source,
                    interpreter=args.python,
                    script=args.script,
                    module=args.module,
                    **common_options,
                )
            elif portable:
                if args.python is not None or args.script is not None or args.module is not None:
                    raise ValueError("Python entry options require --kind python-project")
                manifest = register_portable_folder(
                    store,
                    args.source,
                    executable=args.executable,
                    **common_options,
                )
            else:
                if any(
                    value is not None
                    for value in (args.executable, args.python, args.script, args.module)
                ):
                    raise ValueError("entry selection options do not apply to executable files")
                manifest = register_file(
                    store,
                    args.source,
                    kind=args.kind,
                    **common_options,
                )
            print(
                f"Registered {manifest.app_id} "
                f"({manifest.kind.value}, {manifest.install_mode.value})",
                file=output,
            )
            return 0
        if args.command_name == "list":
            _print_list(store, output)
            return 0
        if args.command_name == "show":
            manifest = store.load(args.app_id)
            print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), file=output)
            return 0
        if args.command_name == "run":
            extra_arguments = list(args.arguments)
            if extra_arguments[:1] == ["--"]:
                extra_arguments.pop(0)
            return run_app(store.load(args.app_id), extra_arguments)
        if args.command_name == "remove":
            plan = build_removal_plan(store, args.app_id)
            print(f"Removal plan for {plan.manifest.app_id}:", file=output)
            for target in plan.existing_targets:
                print(f"  remove [{target.role}] {target.path}", file=output)
            for target in plan.missing_targets:
                print(f"  skip missing [{target.role}] {target.path}", file=output)
            for path in plan.preserved_external:
                print(f"  preserve [external] {path}", file=output)
            for path in plan.unsafe_paths:
                print(f"  BLOCKED [unsafe manifest path] {path}", file=output)
            if plan.unsafe_paths:
                print("Removal is blocked until the manifest is repaired.", file=error_output)
                return 2
            if not args.yes:
                print("Preview only. Re-run with --yes to execute.", file=output)
                return 0
            result = execute_removal(store, plan)
            for path, reason in result.failed:
                print(f"  failed {path}: {reason}", file=error_output)
            if result.manifest_removed:
                print(f"Removed {plan.manifest.app_id} registration.", file=output)
                return 0
            print("Removal incomplete; manifest was preserved.", file=error_output)
            return 2
        if args.command_name == "edit":
            if args.clear_arguments:
                edit_arguments = ()
            else:
                edit_arguments = args.edit_arguments
            if args.clear_working_directory:
                edit_working = None
            elif args.working_directory is not None:
                edit_working = args.working_directory
            else:
                edit_working = UNSET
            manifest = edit_app(
                store,
                args.app_id,
                name=args.name,
                arguments=edit_arguments,
                working_directory=edit_working,
                terminal=args.terminal,
                categories=args.edit_categories,
                startup_notify=args.startup_notify,
                mime_types=args.edit_mime_types,
                desktop_argument=(
                    args.desktop_argument if args.desktop_argument is not None else UNSET
                ),
            )
            print(f"Updated {manifest.app_id}.", file=output)
            return 0
        if args.command_name == "doctor":
            if args.repair:
                repaired, failures = repair(store, args.app_id)
                for repaired_id in repaired:
                    print(f"Repaired {repaired_id}.", file=output)
                for failure in failures:
                    print(f"Repair failed: {failure}", file=error_output)
            report = diagnose(store, args.app_id)
            if not report.checked:
                print("No applications registered.", file=output)
                return 0
            if not report.issues:
                print(f"OK: checked {len(report.checked)} application(s).", file=output)
                return 0
            for issue in report.issues:
                marker = "repairable" if issue.repairable else "manual"
                print(
                    f"{issue.severity.upper()} {issue.app_id} {issue.code} "
                    f"[{marker}]: {issue.message}",
                    file=output,
                )
            return 1
        if args.command_name == "import-gearlever":
            existing = {manifest.source_path for manifest in store.list_manifests()}
            imported = 0
            for candidate in discover_gearlever():
                if str(candidate.source) in existing:
                    print(f"Skipped existing: {candidate.name}", file=output)
                    continue
                register_external_integration(
                    store,
                    candidate.source,
                    name=candidate.name,
                    kind=candidate.kind,
                    command=candidate.command,
                    desktop_entry=candidate.desktop_entry,
                    icon=candidate.icon,
                    terminal=candidate.terminal,
                    categories=candidate.categories,
                    startup_notify=candidate.startup_notify,
                )
                print(f"Imported: {candidate.name}", file=output)
                imported += 1
            print(f"Imported {imported} Gear Lever application(s).", file=output)
            return 0
    except (LocalAppError, ValueError) as exc:
        print(f"localapp: error: {exc}", file=error_output)
        return 2
    parser.error(f"unsupported command: {args.command_name}")
    return 2
