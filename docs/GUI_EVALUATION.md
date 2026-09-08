# GUI status and architecture

LocalAppManager includes a GTK4/libadwaita interface, launched with
`localapp-gui`. See the [README](../README.md) for installation and system
requirements. The current interface is primarily Korean.

## Available workflows

The GUI supports application listing and details, AppImage/executable
registration, portable-folder candidate selection, existing Python project
registration, launch, editing, removal confirmation, doctor diagnostics and
repair, and Gear Lever discovery/import.

Gear Lever discovery reads existing desktop integration. Importing a discovered
application creates a LocalAppManager manifest while preserving the externally
owned Gear Lever integration; it does not create a second desktop entry.

## Shared backend

The GUI calls the same domain services as the CLI. It does not infer removal
targets or user-data locations: removal and diagnostics use backend plans and
issue models.

| Workflow | Backend API |
| --- | --- |
| Application list | `ManifestStore.list_manifests()` |
| Details | `ManifestStore.load()` |
| AppImage/executable registration | `register_file()` |
| Portable-folder registration | `inspect_portable_folder()`, `register_portable_folder()` |
| Python project registration | `register_python_project()` |
| Edit | `edit_app()` |
| Removal | `build_removal_plan()`, `execute_removal()` |
| Diagnostics and repair | `diagnose()`, `repair()` |
| Launch | `launch_app()` |

`launch_app()` starts an argv-based process without waiting for its exit.
Registration/import operations use worker threads and return UI updates through
GLib, keeping file-copy work off the GTK main thread. The backend and CLI do not
require GTK bindings; `gui.py` imports system PyGObject, GTK4, and libadwaita.

## Known limitations and verification

- Large managed copies have no progress percentage or cancellation checkpoints.
- The GUI uses structured inspection results for executable selection.
  Registration errors could also expose structured candidate-selection data for
  other callers instead of listing choices only in an error message.
- `tests/test_gui.py` checks module import and the application ID without creating
  a window. It does not validate interactive workflows or rendered layout.
- Automated interaction and screenshot coverage, broader environment testing,
  and distribution packaging remain roadmap work.
- Flatpak portal requirements have not been settled.

Changes to the UI need manual verification in a graphical session in addition
to the existing tests. See [CONTRIBUTING.md](../CONTRIBUTING.md).

## Historical context

The original evaluation, dated 2026-07-18, recommended deferring a full GUI until
non-blocking launch and copy-progress adapters were available. A subsequent
implementation added the GUI, non-blocking launch, and background registration.
Copy progress and cancellation remain open; the earlier recommendation to avoid
starting GUI implementation no longer describes the project status. The original
environment recorded PyGObject 3.56.3, GTK 4.22.4, and libadwaita 1.9.2; these are
historical observations, not a compatibility matrix.
