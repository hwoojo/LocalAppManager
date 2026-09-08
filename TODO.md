# Post-MVP TODO

The objective's backend and CLI phases are complete. These items are deliberately
outside the current phase scope and should not be implemented implicitly.

## GUI follow-ups

- Add progress and cancellation callbacks to managed file and folder copies.
- Return structured portable candidate-selection data through a service layer.
- Add automated GTK interaction and screenshot tests in a disposable display session.

## Later robustness work

- Add an explicit icon replacement/removal option to `localapp edit`.
- Consider opt-in recovery from a managed copy when an external source vanished.
- Add distribution packaging and end-user installation documentation.
- Evaluate filesystem locking for simultaneous edits of the same application.

## Explicitly out of scope

- DNF, RPM, or Flatpak package management
- automatic dependency installation or source builds
- automatic update discovery
- inferred deletion of user data, configuration, projects, or documents
- recursive removal of unrecorded files
