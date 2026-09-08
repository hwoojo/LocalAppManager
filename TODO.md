# Roadmap

LocalAppManager currently provides a manifest-based backend, CLI, and
GTK4/libadwaita GUI. This roadmap tracks possible improvements, not release
commitments. See [README.md](README.md) for supported features and installation.

## User experience

- [ ] Add progress reporting and cancellation to managed file and folder copies.
- [ ] Expose structured candidate-selection errors for portable registration callers.
- [ ] Add GUI translation support; the current interface is primarily Korean.
- [ ] Add automated GTK interaction and screenshot tests in a disposable display session.
- [ ] Add an explicit icon replacement/removal option to `localapp edit`.

## Reliability and distribution

- [ ] Evaluate filesystem locking for simultaneous edits of the same application.
- [ ] Consider opt-in recovery from a managed copy when an external source vanished.
- [ ] Add distribution packages and validate installation on supported environments.
- [ ] Evaluate portal requirements before introducing Flatpak packaging.

## Outside the project scope

LocalAppManager does not aim to provide:

- DNF, RPM, or Flatpak package management
- automatic dependency installation or source builds
- automatic update discovery
- inferred deletion of user data, configuration, projects, or documents
- recursive removal of unrecorded files

Implementation guidance and safety requirements are in
[CONTRIBUTING.md](CONTRIBUTING.md). GUI-specific limitations are in
[docs/GUI_EVALUATION.md](docs/GUI_EVALUATION.md).
