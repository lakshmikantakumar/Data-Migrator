"""Date, elapsed-time, and timestamp formatting helpers for GMF."""

from __future__ import annotations

from datetime import datetime, timedelta
from time import perf_counter

from .constants import FILE_TIMESTAMP_FORMAT, TIMESTAMP_FORMAT


def current_timestamp() -> str:
    """Return a timestamp suitable for log entries.

    Args:
        None.

    Returns:
        Local timestamp in ``YYYY-MM-DD HH:MM:SS`` form.

    Raises:
        None.

    Notes:
        This shares the timestamp convention used by ``Logger``.
    """
    return datetime.now().strftime(TIMESTAMP_FORMAT)


def file_timestamp() -> str:
    """Return a timestamp suitable for output file names.

    Args:
        None.

    Returns:
        Local timestamp in ``YYYYMMDD_HHMMSS`` form.

    Raises:
        None.

    Notes:
        The format is filesystem-safe on Windows.
    """
    return datetime.now().strftime(FILE_TIMESTAMP_FORMAT)


def start_timer() -> float:
    """Return a high-resolution monotonic timer starting point.

    Args:
        None.

    Returns:
        Performance-counter value.

    Raises:
        None.

    Notes:
        Use with elapsed_seconds rather than wall-clock arithmetic.
    """
    return perf_counter()


def elapsed_seconds(start_time: float) -> float:
    """Return elapsed seconds since a performance-counter starting point.

    Args:
        start_time: Value returned by start_timer.

    Returns:
        Non-negative elapsed seconds rounded to milliseconds.

    Raises:
        ValueError: If start_time is in the future.

    Notes:
        Performance counters are monotonic and unaffected by clock changes.
    """
    elapsed = perf_counter() - start_time
    if elapsed < 0:
        raise ValueError("start_time cannot be in the future.")
    return round(elapsed, 3)


def format_duration(seconds: float) -> str:
    """Format seconds as a readable ``HH:MM:SS`` duration.

    Args:
        seconds: Non-negative duration in seconds.

    Returns:
        Zero-padded duration string.

    Raises:
        ValueError: If seconds is negative.

    Notes:
        Fractional seconds are rounded down for display consistency.
    """
    if seconds < 0:
        raise ValueError("seconds cannot be negative.")
    whole_seconds = int(seconds)
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    return "{:02d}:{:02d}:{:02d}".format(hours, minutes, remaining_seconds)


__all__ = ["current_timestamp", "elapsed_seconds", "file_timestamp", "format_duration", "start_timer"]
