# LocalAppManager

LocalAppManager is a Fedora/GNOME-first tool for tracking applications that
live outside RPM, DNF, and Flatpak. It is designed around an explicit manifest:
files created by LocalAppManager are recorded separately from user-owned source
projects and data.

## Current status: backend, CLI, and GNOME GUI available

The backend now supports linked and managed registration:

- versioned application manifests and JSON serialization
- deterministic application IDs with duplicate handling
- centralized XDG-aware paths
- atomic per-application manifest storage
- explicit errors for invalid or damaged manifests
- linked registration for AppImages and executable files
- listing, JSON detail display, and argv-based execution without a shell
- managed copies under `~/.local/opt/<app-id>/`
- executable wrappers under `~/.local/bin/`
- generated desktop entries under the XDG applications directory
- optional managed icon copies under the XDG icons directory
- exact-path rollback when registration fails
- preview-first, manifest-driven safe removal
- portable-folder inspection and linked/managed registration
- existing Python project registration by script or module
- health diagnostics, safe integration repair, editing, and schema migration
- SHA-256 detection of manually modified managed files

Linked registration never copies or changes the executable source, but its
wrapper, optional icon, and desktop entry are managed files. Removal never
recursively deletes unexpected directory contents.

## Commands

```console
localapp add ~/Applications/MyTool.AppImage
localapp add ~/bin/my-tool --name "My Tool" --arg=--safe-mode
localapp add ~/Downloads/MyTool.AppImage --mode managed --icon ~/Pictures/my-tool.png
localapp add ~/Applications/PortableTool --executable bin/portable-tool
localapp add ~/Projects/MyTool --kind python-project --python ~/Projects/MyTool/.venv/bin/python --module mytool
localapp list
localapp show my-tool
localapp run my-tool -- --one "argument with spaces"
localapp remove my-tool
localapp remove my-tool --yes
localapp edit my-tool --name "My Renamed Tool" --arg=--safe-mode --terminal
localapp doctor
localapp doctor my-tool --repair
localapp import-gearlever
```

`add` accepts only an existing executable file. A `.AppImage` suffix selects the
AppImage kind; other files use the executable kind. Use `--kind` to override the
automatic choice. `--mode linked` is the default; `--mode managed` copies the
executable while preserving the original as external user-owned data. Name
collisions receive stable suffixes such as `my-tool-2`.

Desktop entries support `Name`, `Exec`, `Icon`, `Type`, `Terminal`, `Categories`,
and `StartupNotify`. Use repeated `--category` options and
`--no-startup-notify` to customize them.

`remove` is preview-only unless `--yes` is supplied. The plan distinguishes
existing managed paths, missing paths, preserved external inputs, and unsafe
manifest paths. Unsafe paths block removal; a non-empty managed directory is
left in place and keeps the manifest registered for recovery.

For a portable folder, executable files, `bin` contents, desktop entries,
common icons, and names similar to the folder are inspected. A single executable
candidate is selected automatically. Multiple candidates are reported and must
be resolved with a relative `--executable` path. Managed folder copies reject
special files and links that escape the source tree.

Python projects use Linked mode and an already existing interpreter. Select one
entry form with `--script RELATIVE_PATH` or `--module DOTTED.NAME`; stored
arguments, the working directory, and terminal preference are preserved. The
manager does not create virtual environments or install dependencies.

`edit` can replace the display name, stored arguments, working directory,
terminal flag, categories, and startup-notification setting while updating the
wrapper, desktop entry, and manifest together. `doctor` reports corrupt or old
manifests, missing executables/icons/integration files, external-path loss,
untracked or unsafe managed paths, content mismatches, and duplicate IDs.
`doctor --repair` only regenerates safe integration files and persists supported
manifest migrations; it does not recreate user data or dependencies.

## Development

Python 3.11 or newer is required. The runtime has no third-party dependencies.

```console
python -m pytest
PYTHONPATH=src python -m localapp_manager --help
```

Installing the project creates the `localapp` command:

```console
python -m pip install -e .
localapp --help
```

## Safety boundary

`managed_files` contains only paths created or copied by LocalAppManager.
`external_paths` contains user-owned inputs that must be preserved by default.
Removal operates only from these explicit records rather than guessing which
files belong to an application. External paths are displayed in the removal
plan but are never removal targets.

## GUI status

The GTK4/libadwaita application is installed through the `localapp-gui` entry
point. It provides application listing, AppImage/executable registration,
portable and Python project forms, launch, details, edit, preview-first removal,
doctor diagnostics, and read-only Gear Lever discovery. Registration work runs
off the GTK main thread. Existing Gear Lever desktop entries are reused as
external integration, so importing them does not create duplicate GNOME icons.

The original readiness review and remaining UI limitations are documented in
[`docs/GUI_EVALUATION.md`](docs/GUI_EVALUATION.md).

Remaining post-MVP work is tracked in [`TODO.md`](TODO.md).
