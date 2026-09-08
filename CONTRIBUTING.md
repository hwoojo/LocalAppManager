# Contributing to LocalAppManager

Contributions should preserve the distinction between manager-owned files and
user-owned applications/data. Start with the [README](README.md) for supported
workflows and [roadmap](TODO.md) for possible improvements.

## Development setup

Use Python 3.11 or newer. From a source checkout:

```console
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m localapp_manager --help
```

The backend and CLI have no third-party runtime dependencies. GUI development
also needs system PyGObject, GTK4, and libadwaita as described in the README. To
make system Python bindings visible, create the environment with the matching
system interpreter and `--system-site-packages` instead:

```console
/usr/bin/python3 -m venv --system-site-packages .venv-gui
source .venv-gui/bin/activate
python -m pip install -e ".[dev]"
localapp-gui
```

Use a fresh environment when switching between these setups. GUI launch requires
a graphical desktop session.

## Verification

Run the full suite when system GTK bindings are available:

```console
python -m pytest
```

For backend/CLI work on an environment without GTK bindings:

```console
python -m pytest --ignore=tests/test_gui.py
```

`tests/test_gui.py` imports the GUI without creating a window, but still requires
PyGObject and the GTK/libadwaita typelibs. It is a smoke test, not interaction or
screenshot coverage. Report which test command you ran and any excluded checks
in your pull request.

For GUI changes, also exercise the affected workflow in a graphical session
using disposable sample applications. Check responsiveness, error presentation,
and removal previews. Avoid using valuable application files as test fixtures.

## Code map

All application code lives in `src/localapp_manager/`:

| Area | Modules |
| --- | --- |
| User interfaces | `cli.py`, `gui.py`, `__main__.py` |
| Manifest schema and persistence | `models.py`, `storage.py`, `migrations.py` |
| Paths, identifiers, validation | `paths.py`, `identifiers.py`, `validation.py` |
| Registration | `importers/` |
| Existing integration discovery | `external_sources/gearlever.py` |
| File and desktop integration | `fileops.py`, `desktop.py` |
| Launch, edit, removal | `runners.py`, `editing.py`, `removal.py` |
| Health diagnostics and repair | `doctor.py` |
| Domain errors | `errors.py` |

Tests mirror these areas in `tests/`. Desktop launcher/icon sources live in
`assets/`. Keep domain operations reusable by both interfaces and keep GTK
imports out of backend modules.

## Safety invariants

- `managed_files` records only paths created or copied by LocalAppManager;
  `external_paths` records user-owned inputs that removal must preserve.
- Build removal previews from explicit manifest records. Do not guess related
  files, recursively remove unexpected contents, or bypass unsafe-path checks.
- Preserve the manifest when removal cannot finish, so recovery remains possible.
- Preserve rollback and atomic-write behavior when registration or editing fails.
- Execute commands as argument vectors without a shell. Preserve argument
  boundaries, including whitespace and metacharacters.
- Keep managed-copy validation and content-integrity checks intact. Do not follow
  links outside a portable source tree or silently overwrite modified content.
- Repair may regenerate safe integration files and migrate supported manifests;
  it must not recreate or delete user data or install dependencies.
- Gear Lever integration remains externally owned after import.

Include targeted regression coverage for behavioral changes, especially path
validation, rollback, ownership, and deletion. Tests should use temporary paths
and deterministic fixtures. Describe the concrete behavior change and relevant
verification in a pull request; update user documentation when commands or
requirements change.
