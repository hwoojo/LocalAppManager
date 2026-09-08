# GTK4/libadwaita GUI evaluation

Date: 2026-07-18

## Original Phase 8 decision

Do not start a full GUI implementation yet. The domain backend is ready to be
shared, but two user-interface adapters should be added first: asynchronous
process execution and cancellable progress reporting for managed folder copies.
The CLI is the stable primary interface until those adapters exist.

This decision follows the Phase 8 scope: evaluate a GUI only after the backend
is stable, without expanding the project into an unverified GUI implementation.

## Environment check

The current Fedora environment can import the required bindings:

- PyGObject 3.56.3
- GTK 4.22.4
- libadwaita 1.9.2

These are system dependencies and should remain outside the Python runtime
dependency list. Fedora packaging or setup documentation must declare them when
the GUI is implemented.

## Follow-up implementation

After Phase 8, the user explicitly requested the graphical application. A
GTK4/libadwaita front end is now implemented in `gui.py` and exposed as
`localapp-gui`. Non-blocking process launch is provided by `launch_app()`, and
registration/import work runs on worker threads so the GTK main loop remains
responsive.

The GUI supports listing, details, file/folder/Python registration, portable
candidate selection, launch, edit, removal confirmation, doctor reporting and
repair, and Gear Lever import. Gear Lever desktop integration remains externally
owned and is never deleted by LocalAppManager.

Progress percentages and cancellation checkpoints for very large managed folder
copies remain future work.

## Backend readiness

Only `cli.py` imports `argparse`. Models, storage, importers, desktop generation,
execution, removal, editing, migrations, and doctor diagnostics are reusable
without importing the CLI.

| GUI area | Existing backend API | Status |
| --- | --- | --- |
| Application list | `ManifestStore.list_manifests()` | Ready |
| Details | `ManifestStore.load()` | Ready |
| AppImage/executable registration | `register_file()` | Ready |
| Portable-folder candidate selection | `inspect_portable_folder()` and `register_portable_folder()` | Ready |
| Python project registration | `register_python_project()` | Ready |
| Edit form | `edit_app()` | Ready |
| Removal confirmation | `build_removal_plan()` and `execute_removal()` | Ready |
| Health view | `diagnose()` and `repair()` | Ready |
| Launch action | `launch_app()` | Ready |
| Large managed copy | background worker around importer file operations | Responsive; progress/cancellation still pending |

## Proposed minimal screens

1. Application list with kind, mode, and health badge.
2. Details page showing command, managed paths, and protected external paths.
3. Registration assistant with explicit mode and candidate selection.
4. Removal dialog that renders the existing removal plan before confirmation.
5. Doctor page separating repairable issues from manual intervention.
6. Edit dialog limited to the settings already supported by `edit_app()`.

The UI must not invent removal targets or infer user-data locations. It should
render the backend plan and issue models directly.

## Required work before GUI implementation

- Provide a non-blocking launcher based on `Gio.Subprocess` or a worker adapter.
- Add progress callbacks and cancellation checkpoints to portable-tree copying.
- Expose structured registration-candidate errors rather than formatting all
  choices into one error string.
- Decide whether file chooser access needs Flatpak portals; do not add Flatpak
  packaging until that decision is made.
- Add UI-specific tests separately from backend tests.

## Packaging boundary

The CLI runtime remains standard-library-only. A future GUI extra/package may
depend on system PyGObject, GTK4, and libadwaita, but those dependencies must not
be pulled into the backend merely to make the GUI importable.
