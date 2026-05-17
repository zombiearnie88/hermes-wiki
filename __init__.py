from __future__ import annotations

try:
    from .hermes_wiki import register
except ImportError as error:
    missing_parent = isinstance(error, ModuleNotFoundError) and error.name == (
        __package__ or ""
    ).split(".", 1)[0]
    if __package__ and not missing_parent:
        raise
    from hermes_wiki import register

__all__ = ["register"]
