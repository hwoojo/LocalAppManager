# Usage

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

`add` accepts executable files, portable folders, and existing Python projects.
For file inputs, a `.AppImage` suffix selects the
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


## Gear Lever import

`localapp import-gearlever` discovers Gear Lever desktop entries and creates local
registration manifests. Discovery reads the existing integration; the import
command writes LocalAppManager registrations. Existing desktop entries and app
files stay externally owned, avoiding duplicate launcher icons.

## Storage and removal

| Item | Default location |
| --- | --- |
| Manifests | `~/.local/share/localapp-manager/manifests/` |
| Managed application copies | `~/.local/opt/<app-id>/` |
| Executable wrappers | `~/.local/bin/<app-id>` |
| Desktop entries | `~/.local/share/applications/<app-id>.desktop` |
| Copied icons | `~/.local/share/icons/localapp-manager/` |

`XDG_DATA_HOME` overrides the `~/.local/share` base. Managed application copies
and wrappers remain under `~/.local/opt` and `~/.local/bin`.

`managed_files` records created or copied paths; `external_paths` records
user-owned inputs. Removal uses these records, never inferred ownership or
recursive deletion of unexpected files. Review the preview before using `--yes`.
SHA-256 diagnostics detect changed managed files; this is not a sandbox or a
guarantee that an executable is trustworthy.

Uninstalling the manager with pip does not remove registered apps or their
integration. If you want those removed, preview and remove each registration
before uninstalling LocalAppManager. Keep manifests until cleanup is complete.

[Back to README](../README.md)
