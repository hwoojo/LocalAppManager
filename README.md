# LocalAppManager

Manage Linux applications installed outside RPM, DNF, and Flatpak: AppImages,
standalone executables, portable folders, and existing Python projects.
LocalAppManager provides a CLI and a GTK4/libadwaita GUI, with explicit records
of the files it owns so removal can preserve your original projects and data.

The project is in early development (0.1.0), with Fedora/GNOME as its primary
environment. The GUI currently uses Korean labels; the CLI uses English.

## What it does

- Register apps in **linked** mode (use the original in place) or **managed** mode
  (copy into `~/.local/opt/<app-id>/`). Python projects use linked mode only.
- Create launch wrappers, desktop entries, and optional icon copies.
- Launch apps, edit launch settings, and diagnose or repair integration files.
- Preview removal before deleting explicitly recorded managed paths.
- Import Gear Lever registrations while preserving their existing integration.

It does not install dependencies, build source projects, manage system packages,
or discover updates. Registered programs run with your normal user permissions.

## Install from source

The CLI requires Linux and Python 3.11 or newer, with no third-party runtime
dependencies. Run these commands as your normal user:

```sh
git clone https://github.com/hwoojo/LocalAppManager.git
cd LocalAppManager
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
localapp --help
```

Activate this environment again in new terminals to use the installed commands.
After updating the checkout, run `python -m pip install .` again. For editable
installs and tests, see [Contributing](CONTRIBUTING.md).

### Optional GNOME GUI on Fedora

The GUI also needs system PyGObject, GTK 4.10 or newer, and libadwaita 1.5 or
newer. These requirements follow its use of [Gtk.FileDialog](https://docs.gtk.org/gtk4/class.FileDialog.html)
and [Adw.AlertDialog](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/class.AlertDialog.html).
Install the bindings using the [PyGObject Fedora setup](https://pygobject.gnome.org/getting_started.html#fedora),
plus libadwaita:

```sh
sudo dnf install python3-gobject gtk4 libadwaita
```

From the repository directory, create a separate environment using Fedora's
system Python so it can access those bindings:

```sh
/usr/bin/python3 -m venv --system-site-packages .venv-gui
. .venv-gui/bin/activate
python -m pip install .
localapp-gui
```

A graphical desktop session is required to open the window. Installing with pip
creates commands, but does not install the manager's own GNOME launcher or icon.
See [desktop launcher setup](docs/INSTALLATION.md) for that optional step and
troubleshooting.

## Quick start

Register an already executable AppImage without moving it:

```sh
localapp add ~/Applications/MyTool.AppImage --id my-tool --name "My Tool"
localapp list
localapp show my-tool
localapp run my-tool
```

To copy the app into managed storage instead, supply `--mode managed` when
registering. The original source remains user-owned in either mode.

Inspect app health and preview removal:

```sh
localapp doctor my-tool
localapp remove my-tool
```

Removal only executes when you explicitly run `localapp remove my-tool --yes`.
External inputs are preserved; unexpected contents in managed directories block
complete cleanup and leave the manifest available for recovery.

## Documentation

- [Usage guide](docs/USAGE.md): portable folders, Python projects, editing,
  diagnostics, Gear Lever import, storage paths, and removal.
- [Installation details](docs/INSTALLATION.md): desktop launcher and troubleshooting.
- [Contributing](CONTRIBUTING.md): development setup, tests, and code layout.
- [GUI status](docs/GUI_EVALUATION.md): architecture and current limitations.
- [Roadmap](TODO.md): planned improvements and project scope.

Bug reports and contributions are welcome through
[GitHub issues](https://github.com/hwoojo/LocalAppManager/issues) and pull requests.

## License

[MIT](LICENSE).
