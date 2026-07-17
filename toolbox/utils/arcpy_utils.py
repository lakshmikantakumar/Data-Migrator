"""Safe, testable wrappers around the ArcPy APIs used by GMF."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Generator, Iterable, Optional, Sequence, TypeVar

from .exception_utils import ArcPyOperationError

try:
    import arcpy  # type: ignore
except ImportError:  # pragma: no cover - ArcPy exists only in ArcGIS Pro.
    arcpy = None  # type: ignore

T = TypeVar("T")


@dataclass(frozen=True)
class EnvironmentSettings:
    """Selected ArcPy environment values that GMF must preserve.

    Args:
        workspace: Current ArcPy workspace.
        scratch_workspace: Current ArcPy scratch workspace.
        overwrite_output: Existing overwrite-output setting.
        add_outputs_to_map: Existing add-outputs-to-map setting.

    Raises:
        None.

    Notes:
        Capturing only the settings GMF may need keeps restoration explicit.
    """

    workspace: Any
    scratch_workspace: Any
    overwrite_output: Any
    add_outputs_to_map: Any


def require_arcpy() -> Any:
    """Return ArcPy or raise a clear framework error when it is unavailable.

    Args:
        None.

    Returns:
        The imported ArcPy module.

    Raises:
        ArcPyOperationError: If code is running outside ArcGIS Pro.

    Notes:
        Keeping this check central makes other utility functions testable.
    """
    if arcpy is None:
        raise ArcPyOperationError("ArcPy is unavailable. Run this operation inside ArcGIS Pro.")
    return arcpy


def execute(operation: Callable[..., T], *args: Any, context: Optional[str] = None, **kwargs: Any) -> T:
    """Call an ArcPy operation and convert failures to a framework exception.

    Args:
        operation: ArcPy callable to execute.
        *args: Positional operation arguments.
        context: Optional meaningful operation description.
        **kwargs: Keyword operation arguments.

    Returns:
        Value returned by the ArcPy operation.

    Raises:
        ArcPyOperationError: If ArcPy raises an exception.

    Notes:
        ArcPy messages are included where available, but raw ArcPy exceptions
        never escape this public wrapper.
    """
    api = require_arcpy()
    try:
        return operation(*args, **kwargs)
    except Exception as error:
        messages = _error_messages(api)
        label = context or getattr(operation, "__name__", "ArcPy operation")
        detail = "{} failed: {}".format(label, error)
        if messages:
            detail = "{} ArcPy messages: {}".format(detail, messages)
        raise ArcPyOperationError(detail) from error


def exists(path: str) -> bool:
    """Return whether ArcPy recognizes a catalog path.

    Args:
        path: Catalog path to test.

    Returns:
        ``True`` when ArcPy reports the object exists.

    Raises:
        ArcPyOperationError: If ArcPy cannot inspect the path.

    Notes:
        This wrapper is for geodatabase-aware existence checks.
    """
    return bool(execute(require_arcpy().Exists, path, context="Checking path existence"))


def add_message(message: object) -> None:
    """Write an informational geoprocessing message.

    Args:
        message: Value to display.

    Returns:
        None.

    Raises:
        ArcPyOperationError: If ArcPy cannot publish the message.

    Notes:
        Logger should normally be preferred for durable migration messages.
    """
    execute(require_arcpy().AddMessage, str(message), context="Writing ArcGIS message")


def add_warning(message: object) -> None:
    """Write a warning geoprocessing message.

    Args:
        message: Value to display.

    Returns:
        None.

    Raises:
        ArcPyOperationError: If ArcPy cannot publish the warning.

    Notes:
        This function does not create a persistent log record.
    """
    execute(require_arcpy().AddWarning, str(message), context="Writing ArcGIS warning")


def add_error(message: object) -> None:
    """Write an error geoprocessing message.

    Args:
        message: Value to display.

    Returns:
        None.

    Raises:
        ArcPyOperationError: If ArcPy cannot publish the error.

    Notes:
        This function does not suppress the caller's original error.
    """
    execute(require_arcpy().AddError, str(message), context="Writing ArcGIS error")


def describe(path: str) -> Any:
    """Return ArcPy Describe metadata through the safe operation wrapper.

    Args:
        path: Catalog path to describe.

    Returns:
        ArcPy Describe result.

    Raises:
        ArcPyOperationError: If Describe fails.

    Notes:
        Use GDB metadata cache helpers when repeatedly describing one path.
    """
    return execute(require_arcpy().Describe, path, context="Describing {}".format(path))


def get_messages(severity: int = 2) -> str:
    """Return ArcPy geoprocessing messages at a requested severity.

    Args:
        severity: ArcPy message severity, normally 0, 1, or 2.

    Returns:
        ArcPy message text.

    Raises:
        ArcPyOperationError: If messages cannot be read.

    Notes:
        Severity two is the default because it captures error diagnostics.
    """
    if severity not in (0, 1, 2):
        raise ValueError("severity must be 0, 1, or 2.")
    return str(execute(require_arcpy().GetMessages, severity, context="Reading ArcPy messages"))


def capture_environment() -> EnvironmentSettings:
    """Capture the ArcPy environment settings GMF must preserve.

    Args:
        None.

    Returns:
        Immutable EnvironmentSettings snapshot.

    Raises:
        ArcPyOperationError: If ArcPy is unavailable.

    Notes:
        GMF does not globally set workspace; this supports defensive restore
        when a caller has existing settings.
    """
    environment = require_arcpy().env
    return EnvironmentSettings(
        workspace=environment.workspace,
        scratch_workspace=environment.scratchWorkspace,
        overwrite_output=environment.overwriteOutput,
        add_outputs_to_map=environment.addOutputsToMap,
    )


def restore_environment(settings: EnvironmentSettings) -> None:
    """Restore a previously captured ArcPy environment snapshot.

    Args:
        settings: Settings returned by capture_environment.

    Returns:
        None.

    Raises:
        TypeError: If settings is not an EnvironmentSettings instance.
        ArcPyOperationError: If ArcPy is unavailable.

    Notes:
        Restoration is explicit and does not reset unrelated ArcPy settings.
    """
    if not isinstance(settings, EnvironmentSettings):
        raise TypeError("settings must be an EnvironmentSettings instance.")
    environment = require_arcpy().env
    try:
        environment.workspace = settings.workspace
        environment.scratchWorkspace = settings.scratch_workspace
        environment.overwriteOutput = settings.overwrite_output
        environment.addOutputsToMap = settings.add_outputs_to_map
    except Exception as error:
        raise ArcPyOperationError("Restoring ArcPy environment failed: {}".format(error)) from error


@contextmanager
def preserved_environment() -> Generator[EnvironmentSettings, None, None]:
    """Yield a snapshot and restore selected ArcPy settings on exit.

    Args:
        None.

    Yields:
        Captured EnvironmentSettings.

    Raises:
        ArcPyOperationError: If capture or restoration fails.

    Notes:
        Use around third-party or legacy code that may alter ArcPy settings.
    """
    settings = capture_environment()
    try:
        yield settings
    finally:
        restore_environment(settings)


def safe_execute(operation: Callable[..., T], *args: Any, context: Optional[str] = None, **kwargs: Any) -> T:
    """Execute an ArcPy operation using the framework's exception wrapper.

    Args:
        operation: ArcPy callable to run.
        *args: Positional operation arguments.
        context: Optional operation description.
        **kwargs: Keyword operation arguments.

    Returns:
        Operation result.

    Raises:
        ArcPyOperationError: If the operation fails.

    Notes:
        This descriptive alias is retained for callers using the GMF wording.
    """
    return execute(operation, *args, context=context, **kwargs)


@contextmanager
def search_cursor(feature_class: str, fields: Sequence[str], where_clause: Optional[str] = None) -> Generator[Any, None, None]:
    """Yield a safely constructed ArcPy SearchCursor.

    Args:
        feature_class: Source feature class.
        fields: Fields to read, including geometry tokens when needed.
        where_clause: Optional SQL filter.

    Yields:
        An active ``arcpy.da.SearchCursor``.

    Raises:
        ArcPyOperationError: If cursor creation fails.

    Notes:
        The cursor is always released after the context exits.
    """
    api = require_arcpy()
    try:
        with api.da.SearchCursor(feature_class, list(fields), where_clause) as cursor:
            yield cursor
    except ArcPyOperationError:
        raise
    except Exception as error:
        raise ArcPyOperationError("Opening SearchCursor for {} failed: {}".format(feature_class, error)) from error


@contextmanager
def insert_cursor(feature_class: str, fields: Sequence[str]) -> Generator[Any, None, None]:
    """Yield a safely constructed ArcPy InsertCursor.

    Args:
        feature_class: Target feature class from the template geodatabase.
        fields: Fields to insert, including geometry tokens when needed.

    Yields:
        An active ``arcpy.da.InsertCursor``.

    Raises:
        ArcPyOperationError: If cursor creation or insertion fails.

    Notes:
        UpdateCursor is deliberately not exposed because GMF migrations insert
        transformed data into the copied template schema.
    """
    api = require_arcpy()
    try:
        with api.da.InsertCursor(feature_class, list(fields)) as cursor:
            yield cursor
    except ArcPyOperationError:
        raise
    except Exception as error:
        raise ArcPyOperationError("Opening InsertCursor for {} failed: {}".format(feature_class, error)) from error


def _error_messages(api: Any) -> str:
    """Get ArcPy severity-two messages without masking a primary failure.

    Args:
        api: ArcPy module object.

    Returns:
        Message text or an empty string.

    Raises:
        None.

    Notes:
        This must remain failure-safe because it runs in exception handling.
    """
    try:
        return str(api.GetMessages(2)).strip()
    except Exception:
        return ""


__all__ = [
    "EnvironmentSettings", "add_error", "add_message", "add_warning",
    "capture_environment", "describe", "execute", "exists", "get_messages",
    "insert_cursor", "preserved_environment", "require_arcpy",
    "restore_environment", "safe_execute", "search_cursor",
]
