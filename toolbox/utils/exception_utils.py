"""Framework exceptions and safe exception-formatting helpers."""

from __future__ import annotations

import traceback
from typing import Optional


class GMFError(Exception):
    """Base error for expected Geodatabase Migration Framework failures."""


class ConfigurationError(GMFError):
    """Raised when a required migration configuration is invalid."""


class ValidationError(GMFError):
    """Raised when source, target, or configuration validation fails."""


class MigrationError(GMFError):
    """Raised when a migration operation cannot complete safely."""


class ReportError(GMFError):
    """Raised when a requested CSV report cannot be generated safely."""


class LoggerError(GMFError):
    """Raised when framework logging cannot be initialized or written."""


class ArcPyOperationError(MigrationError):
    """Raised when an ArcPy operation fails behind a safe framework wrapper."""


def format_exception(exception: BaseException, context: Optional[str] = None) -> str:
    """Return a concise exception message suitable for a log entry.

    Args:
        exception: Exception to describe.
        context: Optional operation that was being performed.

    Returns:
        Human-readable exception description.

    Raises:
        None.

    Notes:
        Empty exception messages retain their exception class for diagnostics.
    """
    detail = "{}: {}".format(type(exception).__name__, str(exception) or "No message supplied")
    return "{} failed. {}".format(context, detail) if context else detail


def format_traceback() -> str:
    """Return the active Python traceback as text.

    Args:
        None.

    Returns:
        Traceback text, or an empty string when no exception is active.

    Raises:
        None.

    Notes:
        Call this only from an ``except`` block when an active traceback is
        required.
    """
    return traceback.format_exc()


def raise_migration_error(exception: BaseException, context: str) -> None:
    """Raise a framework MigrationError while retaining the original cause.

    Args:
        exception: Original exception raised by a lower-level operation.
        context: Description of the failed operation.

    Returns:
        None.

    Raises:
        MigrationError: Always, chained from ``exception``.

    Notes:
        Centralizing conversion prevents raw ArcPy exceptions from escaping
        public framework operations.
    """
    raise MigrationError(format_exception(exception, context)) from exception


__all__ = [
    "ArcPyOperationError", "ConfigurationError", "GMFError", "MigrationError",
    "LoggerError", "ReportError", "ValidationError", "format_exception",
    "format_traceback", "raise_migration_error",
]
