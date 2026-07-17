"""Safe standard-library file helpers for GMF configuration and output files."""

from __future__ import annotations

import csv
import os
import shutil
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence

from .constants import CSV_ENCODING
from .exception_utils import ConfigurationError


def resolve_path(path: os.PathLike[str] | str) -> Path:
    """Return an expanded, absolute path without requiring it to exist.

    Args:
        path: Relative or absolute filesystem path.

    Returns:
        Resolved Path object.

    Raises:
        TypeError: If ``path`` is not path-like.

    Notes:
        ``strict=False`` permits callers to resolve intended output paths.
    """
    if not isinstance(path, (str, os.PathLike)):
        raise TypeError("path must be a string or path-like value.")
    return Path(path).expanduser().resolve()


def ensure_folder(folder: os.PathLike[str] | str) -> Path:
    """Create a folder and return its absolute path.

    Args:
        folder: Folder to create if it does not exist.

    Returns:
        Absolute folder path.

    Raises:
        OSError: If the folder cannot be created.

    Notes:
        Existing folders are retained unchanged.
    """
    resolved = resolve_path(folder)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def require_file(path: os.PathLike[str] | str, description: str = "File") -> Path:
    """Validate that a regular file exists.

    Args:
        path: Required file path.
        description: Human-readable name for error messages.

    Returns:
        Absolute path to the existing file.

    Raises:
        ConfigurationError: If the path does not identify a file.

    Notes:
        This is intended for required CSV configuration files.
    """
    resolved = resolve_path(path)
    if not resolved.is_file():
        raise ConfigurationError("{} does not exist: {}".format(description, resolved))
    return resolved


def file_exists(path: os.PathLike[str] | str) -> bool:
    """Return whether a regular file exists at a path.

    Args:
        path: File path to inspect.

    Returns:
        ``True`` only for an existing regular file.

    Raises:
        TypeError: If path is not path-like.

    Notes:
        This is a filesystem check, not an ArcPy catalog-path check.
    """
    return resolve_path(path).is_file()


def folder_exists(path: os.PathLike[str] | str) -> bool:
    """Return whether a folder exists at a path.

    Args:
        path: Folder path to inspect.

    Returns:
        ``True`` only for an existing folder.

    Raises:
        TypeError: If path is not path-like.

    Notes:
        Symbolic-link behavior follows pathlib's standard semantics.
    """
    return resolve_path(path).is_dir()


def safe_delete_file(path: os.PathLike[str] | str, missing_ok: bool = True) -> bool:
    """Delete one regular file without recursively deleting folders.

    Args:
        path: File to delete.
        missing_ok: Whether a missing file should be treated as success.

    Returns:
        ``True`` when a file was removed, otherwise ``False``.

    Raises:
        IsADirectoryError: If the path identifies a directory.
        FileNotFoundError: If missing_ok is false and no file exists.
        OSError: If deletion fails.

    Notes:
        Directory deletion is intentionally excluded to prevent accidental
        removal of a geodatabase folder.
    """
    target = resolve_path(path)
    if target.is_dir():
        raise IsADirectoryError("safe_delete_file cannot delete a folder: {}".format(target))
    if not target.exists():
        if missing_ok:
            return False
        raise FileNotFoundError(target)
    target.unlink()
    return True


def safe_copy_file(
    source: os.PathLike[str] | str,
    destination: os.PathLike[str] | str,
    overwrite: bool = False,
) -> Path:
    """Copy one file while requiring explicit overwrite permission.

    Args:
        source: Existing source file.
        destination: Destination file path.
        overwrite: Whether an existing destination may be replaced.

    Returns:
        Absolute destination path.

    Raises:
        ConfigurationError: If source is missing or destination exists.
        OSError: If the copy cannot be completed.

    Notes:
        Metadata is copied with shutil.copy2 for predictable configuration
        file handling.
    """
    source_path = require_file(source, "Source file")
    destination_path = resolve_path(destination)
    if destination_path.exists() and not overwrite:
        raise ConfigurationError("Destination file already exists: {}".format(destination_path))
    ensure_folder(destination_path.parent)
    shutil.copy2(source_path, destination_path)
    return destination_path


def configuration_file(folder: os.PathLike[str] | str, filename: str) -> Path:
    """Build and validate a configuration-file path within a folder.

    Args:
        folder: Configuration folder.
        filename: Required configuration CSV filename.

    Returns:
        Absolute path to the requested configuration file.

    Raises:
        ConfigurationError: If filename is empty or escapes the folder.

    Notes:
        Path containment prevents ``..`` values in configuration names.
    """
    if not filename or Path(filename).name != filename:
        raise ConfigurationError("Configuration filename must be a plain filename.")
    return resolve_path(resolve_path(folder) / filename)


def copy_template_geodatabase(template_gdb: str, output_gdb: str, overwrite: bool = False) -> str:
    """Copy a template geodatabase through the safe GDB utility.

    Args:
        template_gdb: Existing template geodatabase path.
        output_gdb: Requested target geodatabase path.
        overwrite: Whether an existing target may be replaced.

    Returns:
        Created target geodatabase path.

    Raises:
        MigrationError: If ArcPy cannot perform the geodatabase copy.

    Notes:
        The lazy import prevents a file-helper import from requiring ArcPy.
    """
    from .gdb_utils import copy_template_geodatabase as copy_gdb

    return copy_gdb(template_gdb, output_gdb, overwrite)


def read_csv_rows(
    path: os.PathLike[str] | str,
    required_columns: Optional[Sequence[str]] = None,
    encoding: str = CSV_ENCODING,
) -> List[dict[str, str]]:
    """Read a CSV file into dictionaries and validate its header when needed.

    Args:
        path: CSV file to read.
        required_columns: Optional names that must appear in the header.
        encoding: Text encoding; UTF-8 with BOM support is the GMF default.

    Returns:
        List of rows keyed by the CSV column names.

    Raises:
        ConfigurationError: If the CSV is missing, malformed, or lacks a
            required column.

    Notes:
        Blank rows are omitted and leading/trailing values are normalized.
    """
    csv_path = require_file(path, "Configuration CSV")
    try:
        with csv_path.open("r", encoding=encoding, newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames:
                raise ConfigurationError("CSV has no header row: {}".format(csv_path))
            headers = [header.strip() for header in reader.fieldnames if header]
            _validate_columns(csv_path, headers, required_columns or ())
            return [
                {key.strip(): (value or "").strip() for key, value in row.items() if key}
                for row in reader
                if any((value or "").strip() for value in row.values())
            ]
    except (OSError, csv.Error) as error:
        raise ConfigurationError("Unable to read CSV {}: {}".format(csv_path, error)) from error


def write_csv_rows(
    path: os.PathLike[str] | str,
    field_names: Sequence[str],
    rows: Iterable[Mapping[str, object]],
    encoding: str = CSV_ENCODING,
) -> Path:
    """Write rows to a CSV file with explicit column ordering.

    Args:
        path: Destination CSV file.
        field_names: Ordered output columns.
        rows: Mappings containing output values.
        encoding: Text encoding for the output file.

    Returns:
        Absolute path to the created CSV file.

    Raises:
        ValueError: If no field names are supplied.
        OSError: If the file cannot be written.

    Notes:
        This generic helper does not decide which reports GMF should create.
    """
    if not field_names:
        raise ValueError("At least one CSV field name is required.")
    destination = resolve_path(path)
    ensure_folder(destination.parent)
    with destination.open("w", encoding=encoding, newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(field_names), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return destination


def _validate_columns(path: Path, headers: Sequence[str], required_columns: Sequence[str]) -> None:
    """Validate a CSV header without imposing case-sensitive matching.

    Args:
        path: CSV being checked.
        headers: Actual normalized header names.
        required_columns: Required logical names.

    Returns:
        None.

    Raises:
        ConfigurationError: If any required names are missing.

    Notes:
        Case-insensitive comparison reflects common CSV editing workflows.
    """
    available = {header.casefold() for header in headers}
    missing = [column for column in required_columns if column.casefold() not in available]
    if missing:
        raise ConfigurationError("CSV {} is missing required column(s): {}".format(path, ", ".join(missing)))


__all__ = [
    "configuration_file", "copy_template_geodatabase", "ensure_folder",
    "file_exists", "folder_exists", "read_csv_rows", "require_file",
    "resolve_path", "safe_copy_file", "safe_delete_file", "write_csv_rows",
]
