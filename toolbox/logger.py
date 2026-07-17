"""Application logging for the Geodatabase Migration Framework.

This module provides the framework's single, small logging abstraction.  It
writes a readable ``Migration.log`` file and, when available, mirrors each
entry to the ArcGIS Pro geoprocessing message pane.  It deliberately does not
create reports or maintain report records; that responsibility belongs to
``report.py``.
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from threading import RLock
from time import perf_counter
from types import TracebackType
from typing import Any, Mapping, Optional, Sequence, TextIO, Type

try:
    import arcpy  # type: ignore
except ImportError:  # pragma: no cover - ArcPy is supplied by ArcGIS Pro.
    arcpy = None  # type: ignore


# The names are intentionally repeated here rather than imported from the
# legacy ``utils.py`` module.  This keeps logger.py independently testable and
# prevents an ArcPy-heavy utility module from being loaded only for constants.
LOG_FILE_NAME = "Migration.log"
LOG_INFO = "INFO"
LOG_WARNING = "WARNING"
LOG_ERROR = "ERROR"
LOG_CRITICAL = "CRITICAL"

_VALID_LEVELS = frozenset((LOG_INFO, LOG_WARNING, LOG_ERROR, LOG_CRITICAL))
_DEFAULT_SEPARATOR_WIDTH = 80
_DEFAULT_SEPARATOR_CHARACTER = "-"
_SECTION_CHARACTER = "="
_DEFAULT_ENCODING = "utf-8"
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_SEPARATOR_WIDTH = 250


class Logger:
    """Write migration messages to a file and the ArcGIS message pane.

    A Logger has no external dependencies beyond ArcPy when it is installed.
    It is therefore suitable for unit tests that run outside ArcGIS Pro.  File
    output is flushed for every entry so that useful diagnostic information is
    retained when a geoprocessing tool fails unexpectedly.

    Args:
        log_folder: Folder in which ``Migration.log`` will be created.  A
            supplied path ending with ``.log`` is also accepted as a
            convenience, but its filename is normalized to ``Migration.log``.
        write_to_arcpy: Whether entries should be sent to ArcGIS Pro messages.
        append: Whether initialization appends to an existing log.  The
            default starts a fresh log for each migration run.
        echo_to_console: Whether entries should also be written to stdout.

    Raises:
        OSError: Raised by :meth:`initialize` if the destination cannot be
            created or opened.

    Notes:
        Call :meth:`initialize` before logging.  Calling a logging method
        earlier initializes the logger automatically using its constructor
        settings.
    """

    def __init__(
        self,
        log_folder: Optional[str] = None,
        write_to_arcpy: bool = True,
        append: bool = False,
        echo_to_console: bool = False,
    ) -> None:
        """Create a Logger without opening its output file.

        Args:
            log_folder: Initial folder or requested log-file location.
            write_to_arcpy: Whether ArcGIS Pro receives messages.
            append: Whether the default initialization mode is append.
            echo_to_console: Whether messages are printed to stdout.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Delaying file creation until :meth:`initialize` allows callers to
            build their destination paths before a tool begins execution.
        """
        self._requested_location = log_folder
        self._write_to_arcpy = write_to_arcpy
        self._append = append
        self._echo_to_console = echo_to_console
        self._stream: Optional[TextIO] = None
        self._log_path: Optional[Path] = None
        self._initialized = False
        self._closed = False
        self._lock = RLock()
        self._message_counts = {level: 0 for level in _VALID_LEVELS}
        self._started_at: Optional[float] = None
        self._ended_at: Optional[float] = None

    @property
    def log_path(self) -> Optional[str]:
        """Return the absolute path to the active Migration.log file.

        Args:
            None.

        Returns:
            The active absolute path, or ``None`` before initialization.

        Raises:
            None.

        Notes:
            The returned string is intended for display and diagnostics.  The
            caller should not move or delete the active file.
        """
        return str(self._log_path) if self._log_path is not None else None

    @property
    def initialized(self) -> bool:
        """Return whether the logger currently has an open output stream.

        Args:
            None.

        Returns:
            ``True`` when the logger is ready for file output.

        Raises:
            None.

        Notes:
            A closed logger returns ``False`` and may be initialized again.
        """
        return self._initialized and self._stream is not None

    @property
    def message_counts(self) -> Mapping[str, int]:
        """Return a snapshot of messages written by level.

        Args:
            None.

        Returns:
            A new mapping containing INFO, WARNING, ERROR, and CRITICAL
            counts.

        Raises:
            None.

        Notes:
            The mapping is a copy; modifying it cannot change the logger.
        """
        with self._lock:
            return dict(self._message_counts)

    @property
    def elapsed_seconds(self) -> float:
        """Return elapsed execution time for the active logging session.

        Args:
            None.

        Returns:
            Elapsed seconds rounded to milliseconds, or 0.0 before startup.

        Raises:
            None.

        Notes:
            A monotonic timer is used so system-clock changes cannot alter a
            migration's measured duration.
        """
        with self._lock:
            if self._started_at is None:
                return 0.0
            end_time = self._ended_at if self._ended_at is not None else perf_counter()
            return round(end_time - self._started_at, 3)

    @property
    def elapsed_time(self) -> str:
        """Return elapsed execution time formatted as HH:MM:SS.

        Args:
            None.

        Returns:
            Zero-padded duration text.

        Raises:
            None.

        Notes:
            This property is suitable for migration-summary log entries.
        """
        total_seconds = int(self.elapsed_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return "{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds)

    def initialize(
        self,
        log_folder: Optional[str] = None,
        append: Optional[bool] = None,
    ) -> str:
        """Create the log folder and open ``Migration.log``.

        Args:
            log_folder: Folder for the file.  When omitted, uses the value
                provided to the constructor, then a ``logs`` folder beside
                this module.
            append: Overrides the constructor append setting for this open.

        Returns:
            Absolute path to the opened ``Migration.log`` file.

        Raises:
            OSError: If the folder cannot be made or the file cannot be
                opened.

        Notes:
            Repeated calls are safe.  If the destination is unchanged, the
            existing stream is retained rather than truncating the log.
        """
        with self._lock:
            location = log_folder if log_folder is not None else self._requested_location
            log_path = self._resolve_log_path(location)

            if self.initialized and self._log_path == log_path:
                return str(log_path)

            if self.initialized:
                self.close()

            log_path.parent.mkdir(parents=True, exist_ok=True)
            should_append = self._append if append is None else append
            mode = "a" if should_append else "w"
            self._stream = log_path.open(mode=mode, encoding=_DEFAULT_ENCODING)
            self._log_path = log_path
            self._initialized = True
            self._closed = False
            self._started_at = perf_counter()
            self._ended_at = None

            self._write_header(append=should_append)
            return str(log_path)

    def info(self, message: Any) -> None:
        """Write an informational message.

        Args:
            message: Value to convert to text and log.

        Returns:
            None.

        Raises:
            OSError: If the log file cannot be written.

        Notes:
            INFO messages use ``arcpy.AddMessage`` when ArcPy is available.
        """
        self._log(LOG_INFO, message)

    def warning(self, message: Any) -> None:
        """Write a warning message.

        Args:
            message: Value to convert to text and log.

        Returns:
            None.

        Raises:
            OSError: If the log file cannot be written.

        Notes:
            WARNING messages use ``arcpy.AddWarning`` when available.
        """
        self._log(LOG_WARNING, message)

    def error(self, message: Any) -> None:
        """Write an error message.

        Args:
            message: Value to convert to text and log.

        Returns:
            None.

        Raises:
            OSError: If the log file cannot be written.

        Notes:
            ERROR messages use ``arcpy.AddError`` when available.
        """
        self._log(LOG_ERROR, message)

    def critical(self, message: Any) -> None:
        """Write a critical, migration-stopping message.

        Args:
            message: Value to convert to text and log.

        Returns:
            None.

        Raises:
            OSError: If the log file cannot be written.

        Notes:
            Critical messages appear as ArcGIS errors because ArcPy has no
            separate critical-message API.
        """
        self._log(LOG_CRITICAL, message)

    def section(self, title: Any, width: int = _DEFAULT_SEPARATOR_WIDTH) -> None:
        """Write a conspicuous section heading without an artificial level.

        Args:
            title: Heading text for the next logical migration operation.
            width: Total width of the heading decoration.

        Returns:
            None.

        Raises:
            ValueError: If ``width`` is outside the supported range.
            OSError: If the log file cannot be written.

        Notes:
            The section is mirrored as an informational ArcGIS message.
        """
        normalized_width = self._validate_width(width)
        heading = " {} ".format(self._normalize_message(title))
        decorated = heading.center(normalized_width, _SECTION_CHARACTER)
        self.info(decorated)

    def separator(
        self,
        character: str = _DEFAULT_SEPARATOR_CHARACTER,
        width: int = _DEFAULT_SEPARATOR_WIDTH,
    ) -> None:
        """Write an informational horizontal separator.

        Args:
            character: Single character used to build the separator.
            width: Number of repeated characters to write.

        Returns:
            None.

        Raises:
            ValueError: If the character or width is invalid.
            OSError: If the log file cannot be written.

        Notes:
            Separators are emitted as INFO messages and therefore include a
            timestamp in the file and appear in ArcGIS Pro.
        """
        if not isinstance(character, str) or len(character) != 1:
            raise ValueError("Separator character must be exactly one character.")
        self.info(character * self._validate_width(width))

    def exception(
        self,
        exception: BaseException,
        context: Optional[str] = None,
        include_traceback: bool = True,
        exc_info: Optional[
            tuple[Type[BaseException], BaseException, Optional[TracebackType]]
        ] = None,
    ) -> None:
        """Log an exception and, when available, its Python traceback.

        Args:
            exception: Exception object being handled.
            context: Optional description of the operation that failed.
            include_traceback: Whether to include traceback text in the log.
            exc_info: Explicit exception triple.  Supply this when logging an
                exception outside its active ``except`` block.

        Returns:
            None.

        Raises:
            OSError: If the log file cannot be written.

        Notes:
            Traceback lines are written to the log only, avoiding a noisy
            geoprocessing message pane.  The exception summary is sent to
            ArcGIS using ERROR level.
        """
        if not isinstance(exception, BaseException):
            raise TypeError("exception must derive from BaseException.")

        summary = self._format_exception_summary(exception, context)
        self.error(summary)
        if not include_traceback:
            return

        exception_details = exc_info if exc_info is not None else sys.exc_info()
        if exception_details[0] is None:
            exception_details = (type(exception), exception, exception.__traceback__)
        traceback_text = "".join(traceback.format_exception(*exception_details)).rstrip()
        if traceback_text:
            self._log(LOG_ERROR, traceback_text, send_to_arcpy=False)

    def statistics(
        self,
        title: str,
        values: Mapping[str, Any],
        sort_keys: bool = False,
    ) -> None:
        """Log a compact group of named migration statistics.

        Args:
            title: Label describing the collection of metrics.
            values: Names and values to include.  Values are displayed only;
                they are not converted into report data.
            sort_keys: Whether names should be written alphabetically.

        Returns:
            None.

        Raises:
            TypeError: If ``values`` is not a mapping.
            OSError: If the log file cannot be written.

        Notes:
            This method is presentation-only and intentionally does not
            generate a CSV, report object, or any report artifact.
        """
        if not isinstance(values, Mapping):
            raise TypeError("values must be a mapping of statistic names to values.")

        self.section(title)
        items = values.items()
        if sort_keys:
            items = ((key, values[key]) for key in sorted(values, key=lambda item: str(item)))
        for name, value in items:
            self.info("{:<30} : {}".format(str(name), self._normalize_message(value)))

    def close(self) -> None:
        """Flush and close the current log file.

        Args:
            None.

        Returns:
            None.

        Raises:
            OSError: If buffered file data cannot be flushed or closed.

        Notes:
            Calling close more than once is safe.  The logger may be reopened
            by a subsequent call to :meth:`initialize`.
        """
        with self._lock:
            if self._stream is not None:
                try:
                    self._ended_at = perf_counter()
                    self._log(
                        LOG_INFO,
                        "Log completed. Execution time: {}.".format(self.elapsed_time),
                        send_to_arcpy=False,
                    )
                    self._stream.flush()
                finally:
                    self._stream.close()
            self._stream = None
            self._initialized = False
            self._closed = True

    def __enter__(self) -> "Logger":
        """Initialize the logger for use in a context manager.

        Args:
            None.

        Returns:
            The initialized Logger instance.

        Raises:
            OSError: If initialization cannot open the log file.

        Notes:
            Context-manager use guarantees :meth:`close` is attempted.
        """
        self.initialize()
        return self

    def __exit__(
        self,
        exception_type: Optional[Type[BaseException]],
        exception_value: Optional[BaseException],
        exception_traceback: Optional[TracebackType],
    ) -> bool:
        """Close the logger when its context manager exits.

        Args:
            exception_type: Type of an exception raised in the context.
            exception_value: Exception raised in the context, if any.
            exception_traceback: Traceback associated with that exception.

        Returns:
            Always ``False`` so caller exceptions are never suppressed.

        Raises:
            OSError: If the log file cannot be closed.

        Notes:
            An exception escaping the context is first logged as CRITICAL with
            its traceback before the stream is closed.
        """
        if exception_value is not None:
            self.critical("Unhandled exception while executing migration.")
            self.exception(
                exception_value,
                include_traceback=True,
                exc_info=(exception_type or type(exception_value), exception_value, exception_traceback),
            )
        self.close()
        return False

    def _log(self, level: str, message: Any, send_to_arcpy: bool = True) -> None:
        """Write one normalized message and optionally mirror it to ArcPy.

        Args:
            level: Valid framework log level.
            message: Value to write.
            send_to_arcpy: Whether to mirror this entry to ArcGIS Pro.

        Returns:
            None.

        Raises:
            ValueError: If ``level`` is unsupported.
            OSError: If the log file cannot be written.

        Notes:
            ArcPy output failures are intentionally ignored: logging must not
            obscure the original migration error due to a UI messaging issue.
        """
        if level not in _VALID_LEVELS:
            raise ValueError("Unsupported log level: {}".format(level))

        text = self._normalize_message(message)
        with self._lock:
            self._ensure_initialized()
            timestamp = self._timestamp()
            entry = self._format_entry(timestamp, level, text)
            assert self._stream is not None
            self._stream.write(entry + "\n")
            self._stream.flush()
            self._message_counts[level] += 1

        if send_to_arcpy:
            self._write_arcpy_message(level, text)
        if self._echo_to_console:
            print(entry)

    def _ensure_initialized(self) -> None:
        """Initialize the logger when a caller logs before explicit setup.

        Args:
            None.

        Returns:
            None.

        Raises:
            OSError: If automatic initialization cannot open the log file.

        Notes:
            This keeps the public methods forgiving while still producing the
            required migration log.
        """
        if not self.initialized:
            self.initialize()

    def _resolve_log_path(self, location: Optional[str]) -> Path:
        """Resolve a requested location into an absolute Migration.log path.

        Args:
            location: Folder or optional file-like location.

        Returns:
            Absolute path whose filename is always ``Migration.log``.

        Raises:
            TypeError: If location is not a path string or ``None``.

        Notes:
            Treating an existing ``.log`` request as its parent folder avoids
            accidental generation of multiple differently named logs.
        """
        if location is None:
            folder = Path(__file__).resolve().parent / "logs"
        elif not isinstance(location, (str, os.PathLike)):
            raise TypeError("log_folder must be a path string, Path, or None.")
        else:
            requested_path = Path(location).expanduser()
            folder = requested_path.parent if requested_path.suffix.lower() == ".log" else requested_path
        return (folder / LOG_FILE_NAME).resolve()

    def _write_header(self, append: bool) -> None:
        """Write a short run marker after a log file is opened.

        Args:
            append: Whether the file was opened in append mode.

        Returns:
            None.

        Raises:
            OSError: If the header cannot be written.

        Notes:
            The header is file-only so it does not add framework boilerplate
            to the ArcGIS message pane.
        """
        mode = "continued" if append else "started"
        self._log(LOG_INFO, "Geodatabase Migration Framework log {}.".format(mode), False)
        self._log(LOG_INFO, "Log file: {}".format(self.log_path), False)

    @staticmethod
    def _timestamp() -> str:
        """Return the current local timestamp for a log entry.

        Args:
            None.

        Returns:
            Timestamp formatted as ``YYYY-MM-DD HH:MM:SS``.

        Raises:
            None.

        Notes:
            Local time is appropriate because logs are reviewed alongside the
            ArcGIS Pro session that executed the migration.
        """
        return datetime.now().strftime(_TIMESTAMP_FORMAT)

    @staticmethod
    def _format_entry(timestamp: str, level: str, message: str) -> str:
        """Format a possibly multi-line message as timestamped log entries.

        Args:
            timestamp: Timestamp for the entire logical entry.
            level: Valid log-level label.
            message: Normalized text to format.

        Returns:
            Text containing one or more file-log lines.

        Raises:
            None.

        Notes:
            Each traceback line receives a prefix to keep the log searchable
            and prevent unlabelled output.
        """
        prefix = "{} | {:8} | ".format(timestamp, level)
        return "\n".join(prefix + line for line in message.splitlines() or [""])

    @staticmethod
    def _normalize_message(message: Any) -> str:
        """Convert a message value into safe, consistently terminated text.

        Args:
            message: Any value supplied to a public logging method.

        Returns:
            String representation with trailing newlines removed.

        Raises:
            None.

        Notes:
            ``None`` is rendered explicitly, which is more useful during
            diagnostics than silently writing an empty message.
        """
        return str(message).replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")

    @staticmethod
    def _validate_width(width: int) -> int:
        """Validate a display-line width.

        Args:
            width: Proposed count of characters.

        Returns:
            The accepted width.

        Raises:
            ValueError: If the width is not an integer in the allowed range.

        Notes:
            The upper limit prevents accidental creation of huge message-pane
            entries from a malformed configuration value.
        """
        if isinstance(width, bool) or not isinstance(width, int):
            raise ValueError("Separator width must be an integer.")
        if not 1 <= width <= _MAX_SEPARATOR_WIDTH:
            raise ValueError("Separator width must be between 1 and {}.".format(_MAX_SEPARATOR_WIDTH))
        return width

    @staticmethod
    def _format_exception_summary(exception: BaseException, context: Optional[str]) -> str:
        """Build an actionable one-line exception message.

        Args:
            exception: Exception that was caught.
            context: Optional operation description.

        Returns:
            Formatted exception summary.

        Raises:
            None.

        Notes:
            The exception class is retained even when an exception has no
            message, which makes empty ArcPy failures diagnosable.
        """
        description = "{}: {}".format(type(exception).__name__, str(exception) or "No message supplied")
        return "{} failed. {}".format(context, description) if context else description

    def _write_arcpy_message(self, level: str, message: str) -> None:
        """Mirror a message to the appropriate ArcPy geoprocessing method.

        Args:
            level: Valid framework log level.
            message: Message text without the file prefix.

        Returns:
            None.

        Raises:
            None.

        Notes:
            All ArcPy errors are swallowed deliberately.  ArcPy messaging is
            a secondary destination; the file logger remains authoritative.
        """
        if not self._write_to_arcpy or arcpy is None:
            return
        try:
            if level == LOG_INFO:
                arcpy.AddMessage(message)
            elif level == LOG_WARNING:
                arcpy.AddWarning(message)
            else:
                arcpy.AddError(message)
        except Exception:
            # Do not let ArcPy UI messaging hide an original migration error.
            pass


__all__: Sequence[str] = (
    "LOG_CRITICAL",
    "LOG_ERROR",
    "LOG_FILE_NAME",
    "LOG_INFO",
    "LOG_WARNING",
    "Logger",
)
