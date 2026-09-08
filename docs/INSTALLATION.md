# Installation details

Start with the [source installation instructions](../README.md#install-from-source).
There is no distribution package or automatic desktop-asset installer in this
repository yet. The checked-in desktop entry and SVG icon are installation assets.

## Optional desktop launcher

After installing the GUI, copy its assets as your normal user:

```sh
mkdir -p "${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
cp assets/io.github.hwoo.LocalAppManager.desktop "${XDG_DATA_HOME:-$HOME/.local/share}/applications/"
cp assets/io.github.hwoo.LocalAppManager.svg "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/"
```

The supplied desktop entry uses `Exec=localapp-gui`, which requires the command
to be on the **desktop session's PATH**. Activating a virtual environment in a
terminal does not change GNOME's PATH. For the README's virtual environment
installation, edit the copied desktop entry and replace its `Exec` line with the
absolute executable path printed by:

```sh
.venv-gui/bin/python -c 'import sys; print(sys.prefix + "/bin/localapp-gui")'
```

For example, use `Exec="/absolute/path/to/LocalAppManager/.venv-gui/bin/localapp-gui"`.
Use your actual path, not the example. Desktop entries do not expand `~` or `$HOME`.
Keep the virtual environment at that location while the launcher is installed.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `localapp: command not found` | Activate the environment used for installation. |
| `No module named gi` | Install system PyGObject and use `/usr/bin/python3` with `--system-site-packages` for the GUI environment. |
| GTK or Adw namespace unavailable | Install `gtk4` and `libadwaita` system packages. |
| Missing `FileDialog`, `Dialog`, or `AlertDialog` | Check the GTK/libadwaita minimum versions in the README. |
| GUI cannot open a display | Launch from an active graphical desktop session. |
| A registered app no longer starts | Run `localapp doctor <app-id>`; linked sources and Python interpreters must still exist. |
| Desktop launch fails but terminal launch works | Check the copied desktop entry's absolute `Exec` path. |

LocalAppManager does not make source files executable or install application
runtime dependencies. Verify that the original app can run before registering it.
`doctor --repair` repairs safe integration files and supported manifest versions;
it cannot restore a missing project, interpreter, or dependency.

## Uninstall

If you want registered applications removed, first review their individual
`localapp remove <app-id>` plans and explicitly execute the desired removals.
Uninstalling the manager itself leaves registrations and managed copies intact.

Activate the environment where the manager was installed and run:

```sh
python -m pip uninstall localapp-manager
```

If you installed the optional desktop assets above, remove those two exact files:

```sh
rm "${XDG_DATA_HOME:-$HOME/.local/share}/applications/io.github.hwoo.LocalAppManager.desktop"
rm "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/io.github.hwoo.LocalAppManager.svg"
```

[Back to README](../README.md)
