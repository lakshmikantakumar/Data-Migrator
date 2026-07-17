"""ArcGIS Pro progressor helpers with a testable progress state object."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Optional

from . import arcpy_utils
from .exception_utils import ArcPyOperationError


@dataclass
class ProgressState:
    """Track safe progress values for one bounded migration operation.

    Args:
        total: Number of expected work items.
        current: Number of completed work items.
        label: Current descriptive progress label.

    Raises:
        ValueError: If total or current is invalid.

    Notes:
        The class has no ArcPy dependency and can be unit-tested directly.
    """

    total: int
    current: int = 0
    label: str = "Processing"

    def __post_init__(self) -> None:
        """Validate initial state.

        Args:
            None.

        Returns:
            None.

        Raises:
            ValueError: If total is negative or current is out of bounds.

        Notes:
            A zero total is allowed for an empty feature class list.
        """
        if isinstance(self.total, bool) or self.total < 0:
            raise ValueError("total must be a non-negative integer.")
        if not 0 <= self.current <= self.total:
            raise ValueError("current must be between zero and total.")

    @property
    def percent(self) -> float:
        """Return completion percentage without division by zero.

        Args:
            None.

        Returns:
            Percentage from 0.0 through 100.0.

        Raises:
            None.

        Notes:
            An empty operation is considered complete.
        """
        return 100.0 if self.total == 0 else round(self.current * 100.0 / self.total, 2)

    def advance(self, count: int = 1, label: Optional[str] = None) -> int:
        """Advance progress without exceeding its declared total.

        Args:
            count: Number of completed items to add.
            label: Optional replacement progress label.

        Returns:
            Updated current position.

        Raises:
            ValueError: If count is negative or advancement exceeds total.

        Notes:
            Strict bounds expose incorrect migration accounting early.
        """
        if isinstance(count, bool) or count < 0:
            raise ValueError("count must be a non-negative integer.")
        if self.current + count > self.total:
            raise ValueError("progress cannot exceed total.")
        self.current += count
        if label is not None:
            self.label = label
        return self.current


class ProgressManager:
    """Manage ArcGIS progress, elapsed time, and formatted status text.

    Args:
        total: Number of expected work items.
        label: Initial ArcGIS progressor label.

    Raises:
        ValueError: If total is invalid.

    Notes:
        Call start before update, then finish in a finally block or use the
        manager as a context manager.
    """

    def __init__(self, total: int, label: str = "Processing") -> None:
        """Create a manager without altering the ArcGIS progressor.

        Args:
            total: Number of expected work items.
            label: Initial display label.

        Returns:
            None.

        Raises:
            ValueError: If total is invalid.

        Notes:
            ProgressState validation is performed immediately.
        """
        self.state = ProgressState(total=total, label=label)
        self._started_at: Optional[float] = None
        self._finished_at: Optional[float] = None

    @property
    def elapsed_seconds(self) -> float:
        """Return elapsed wall-independent execution time in seconds.

        Args:
            None.

        Returns:
            Elapsed duration rounded to milliseconds, or 0.0 before start.

        Raises:
            None.

        Notes:
            Uses perf_counter so system-clock changes do not affect duration.
        """
        if self._started_at is None:
            return 0.0
        end_time = self._finished_at if self._finished_at is not None else perf_counter()
        return round(end_time - self._started_at, 3)

    @property
    def elapsed_text(self) -> str:
        """Return elapsed time formatted as HH:MM:SS.

        Args:
            None.

        Returns:
            Formatted elapsed duration.

        Raises:
            None.

        Notes:
            This is suited to migration summaries and progress labels.
        """
        return format_elapsed_time(self.elapsed_seconds)

    def start(self) -> ProgressState:
        """Start timing and initialize the ArcGIS step progressor.

        Args:
            None.

        Returns:
            Active ProgressState.

        Raises:
            ArcPyOperationError: If ArcGIS progressor setup fails.

        Notes:
            Repeated calls do not reset elapsed time or completed progress.
        """
        if self._started_at is None:
            self._started_at = perf_counter()
            self.state = initialize_progress(self.state.total, self.state.label)
        return self.state

    def update(self, label: Optional[str] = None, advance_by: int = 1) -> ProgressState:
        """Advance the progressor and return its current state.

        Args:
            label: Optional replacement display label.
            advance_by: Number of completed work items.

        Returns:
            Updated ProgressState.

        Raises:
            RuntimeError: If start has not been called.
            ArcPyOperationError: If ArcPy progress update fails.

        Notes:
            The label can be generated by format_progress for consistency.
        """
        if self._started_at is None:
            raise RuntimeError("ProgressManager.start must be called before update.")
        return update_progress(self.state, label, advance_by)

    def finish(self) -> float:
        """Reset the ArcGIS progressor and return total elapsed seconds.

        Args:
            None.

        Returns:
            Final elapsed time in seconds.

        Raises:
            ArcPyOperationError: If ArcPy cannot reset the progressor.

        Notes:
            It is safe to call finish more than once after a successful start.
        """
        if self._started_at is not None and self._finished_at is None:
            self._finished_at = perf_counter()
            reset_progress()
        return self.elapsed_seconds

    def __enter__(self) -> "ProgressManager":
        """Start progress management for a context block.

        Args:
            None.

        Returns:
            This started ProgressManager.

        Raises:
            ArcPyOperationError: If progressor initialization fails.

        Notes:
            Context exit always attempts to reset the ArcGIS progressor.
        """
        self.start()
        return self

    def __exit__(self, exception_type: object, exception_value: object, traceback: object) -> bool:
        """Finish progress management without suppressing caller exceptions.

        Args:
            exception_type: Escaping exception type, if any.
            exception_value: Escaping exception value, if any.
            traceback: Escaping exception traceback, if any.

        Returns:
            Always ``False``.

        Raises:
            ArcPyOperationError: If progressor reset fails.

        Notes:
            Original exceptions continue to propagate to caller error handling.
        """
        self.finish()
        return False


def initialize_progress(total: int, label: str = "Processing") -> ProgressState:
    """Initialize ArcGIS Pro's step progressor and return its state.

    Args:
        total: Number of expected steps.
        label: Initial label shown in ArcGIS Pro.

    Returns:
        Newly initialized ProgressState.

    Raises:
        ValueError: If total is invalid.
        ArcPyOperationError: If ArcPy cannot initialize the progressor.

    Notes:
        This does not modify ``arcpy.env`` settings.
    """
    state = ProgressState(total=total, label=label)
    api = arcpy_utils.require_arcpy()
    arcpy_utils.execute(api.SetProgressor, "step", label, 0, total, 1, context="Initializing progressor")
    return state


def update_progress(state: ProgressState, label: Optional[str] = None, advance_by: int = 1) -> ProgressState:
    """Advance a progress state and update ArcGIS Pro's progressor.

    Args:
        state: Progress state returned by initialize_progress.
        label: Optional label to show for the updated step.
        advance_by: Number of steps to advance.

    Returns:
        The same updated ProgressState instance.

    Raises:
        TypeError: If state is not ProgressState.
        ValueError: If progression is invalid.
        ArcPyOperationError: If ArcPy cannot update the progressor.

    Notes:
        State is advanced before ArcPy is called so caller accounting stays
        explicit if an ArcPy UI update subsequently fails.
    """
    if not isinstance(state, ProgressState):
        raise TypeError("state must be a ProgressState instance.")
    state.advance(advance_by, label)
    api = arcpy_utils.require_arcpy()
    arcpy_utils.execute(api.SetProgressorLabel, state.label, context="Setting progressor label")
    arcpy_utils.execute(api.SetProgressorPosition, state.current, context="Updating progressor position")
    return state


def reset_progress() -> None:
    """Reset ArcGIS Pro's progressor after an operation finishes.

    Args:
        None.

    Returns:
        None.

    Raises:
        ArcPyOperationError: If ArcPy cannot reset the progressor.

    Notes:
        Call in a ``finally`` block at the outer migration-operation level.
    """
    api = arcpy_utils.require_arcpy()
    arcpy_utils.execute(api.ResetProgressor, context="Resetting progressor")


def format_elapsed_time(seconds: float) -> str:
    """Format a non-negative duration as HH:MM:SS.

    Args:
        seconds: Elapsed duration in seconds.

    Returns:
        Zero-padded elapsed-time text.

    Raises:
        ValueError: If seconds is negative.

    Notes:
        Fractional seconds are omitted for concise geoprocessing labels.
    """
    if seconds < 0:
        raise ValueError("seconds cannot be negative.")
    hours, remainder = divmod(int(seconds), 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    return "{:02d}:{:02d}:{:02d}".format(hours, minutes, remaining_seconds)


def format_progress(current: int, total: int, label: str = "Processing") -> str:
    """Return a consistent human-readable progress label.

    Args:
        current: Completed item count.
        total: Expected item count.
        label: Operation description.

    Returns:
        Progress label including percentage.

    Raises:
        ValueError: If counts are invalid.

    Notes:
        A zero total is rendered as a completed empty operation.
    """
    state = ProgressState(total=total, current=current, label=label)
    return "{}: {}/{} ({:.2f}%)".format(state.label, state.current, state.total, state.percent)


__all__ = [
    "ProgressManager", "ProgressState", "format_elapsed_time", "format_progress",
    "initialize_progress", "reset_progress", "update_progress",
]
