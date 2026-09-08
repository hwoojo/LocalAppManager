"""Application registration backends."""

from .file import register_file
from .external import register_external_integration
from .linked_file import register_linked_file
from .portable import inspect_portable_folder, register_portable_folder
from .python_project import register_python_project

__all__ = [
    "inspect_portable_folder",
    "register_file",
    "register_external_integration",
    "register_linked_file",
    "register_portable_folder",
    "register_python_project",
]
