"""Main workflow controller for the Geodatabase Migration Framework.

Transformer coordinates logging, typed configuration loading, validation,
template copying, migration, and CSV reporting.  It is the only module that
orchestrates the complete migration lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence

try:  # Supports package imports and ArcGIS Python-toolbox top-level imports.
    from .logger import Logger
    from .migrator import MigrationSummary, Migrator
    from .report import AuditEvent, ReportPaths, generate_reports
    from .rules import RuleSet, load_configuration
    from .utils.constants import (
        EXECUTION_MODES, MODE_GENERATE_REPORT, MODE_MIGRATE_ONLY,
        MODE_VALIDATE_AND_MIGRATE, MODE_VALIDATE_ONLY,
    )
    from .utils.exception_utils import ConfigurationError, GMFError
    from .validator import ValidationSummary, Validator
except ImportError:  # pragma: no cover - exercised by ArcGIS toolbox loading.
    from logger import Logger  # type: ignore
    from migrator import MigrationSummary, Migrator  # type: ignore
    from report import AuditEvent, ReportPaths, generate_reports  # type: ignore
    from rules import RuleSet, load_configuration  # type: ignore
    from utils.constants import (  # type: ignore
        EXECUTION_MODES, MODE_GENERATE_REPORT, MODE_MIGRATE_ONLY,
        MODE_VALIDATE_AND_MIGRATE, MODE_VALIDATE_ONLY,
    )
    from utils.exception_utils import ConfigurationError, GMFError  # type: ignore
    from validator import ValidationSummary, Validator  # type: ignore


class ExecutionStatus(str, Enum):
    """Terminal statuses returned by the main GMF controller."""

    SUCCESS = "SUCCESS"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    MIGRATION_FAILED = "MIGRATION_FAILED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ExecutionResult:
    """Complete final status returned by Transformer.run.

    Args:
        status: Terminal execution status.
        message: Concise human-readable outcome.
        output_gdb: Output GDB path when a migration path was attempted.
        log_path: Migration.log path when logger initialized successfully.
        validation_summary: Optional validation output.
        migration_summary: Optional migration output.
        report_paths: Optional paths for generated CSV reports.
        audit_events: Auditable workflow events.

    Raises:
        None.

    Notes:
        Callers should inspect this value rather than infer workflow outcome
        from ArcGIS message text.
    """

    status: ExecutionStatus
    message: str
    output_gdb: Optional[str]
    log_path: Optional[str]
    validation_summary: Optional[ValidationSummary]
    migration_summary: Optional[MigrationSummary]
    report_paths: Optional[ReportPaths]
    audit_events: Sequence[AuditEvent]

    @property
    def succeeded(self) -> bool:
        """Return whether the requested workflow completed successfully.

        Args:
            None.

        Returns:
            ``True`` only for SUCCESS status.

        Raises:
            None.

        Notes:
            Validation warnings may exist in a successful result.
        """
        return self.status is ExecutionStatus.SUCCESS


class _NullLogger:
    """No-op Logger-compatible object used when detailed logging is disabled."""

    log_path: Optional[str] = None

    def initialize(self) -> Optional[str]:
        """Return no log path because output is disabled.

        Args:
            None.

        Returns:
            None.

        Raises:
            None.

        Notes:
            This keeps the controller workflow independent of logging choice.
        """
        return None

    def close(self) -> None:
        """Perform no cleanup for a disabled logger.

        Args:
            None.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Method exists for Logger-compatible lifecycle handling.
        """
        return None

    def section(self, *args: object, **kwargs: object) -> None:
        """Ignore a section message when logging is disabled.

        Args:
            *args: Ignored positional values.
            **kwargs: Ignored keyword values.

        Returns:
            None.

        Raises:
            None.

        Notes:
            The same behavior applies to all dynamic log levels below.
        """
        return None

    info = section
    warning = section
    error = section
    critical = section
    exception = section
    statistics = section


class Transformer:
    """Coordinate the GMF end-to-end workflow without schema modification.

    Args:
        configuration_folder: Folder containing GMF configuration CSV files.
        source_gdb: Source geodatabase catalog path.
        template_gdb: Template geodatabase catalog path.
        output_gdb: Requested copied-template output GDB path.
        execution_mode: One configured GMF execution mode.
        overwrite_output: Whether an existing output GDB may be replaced.
        report_folder: Optional destination for all CSV reports.
        log_folder: Optional destination for Migration.log.

    Raises:
        ValueError: If required paths or execution mode are invalid.

    Notes:
        The template is copied only after successful validation, and only for
        modes that perform migration.
    """

    def __init__(
        self,
        configuration_folder: str,
        source_gdb: str,
        template_gdb: str,
        output_gdb: str,
        execution_mode: str = MODE_VALIDATE_AND_MIGRATE,
        overwrite_output: bool = False,
        report_folder: Optional[str] = None,
        log_folder: Optional[str] = None,
        generate_log: bool = True,
    ) -> None:
        """Capture immutable workflow inputs and derive output folder defaults.

        Args:
            configuration_folder: Required configuration location.
            source_gdb: Required source workspace.
            template_gdb: Required template workspace.
            output_gdb: Required output workspace path.
            execution_mode: Validate, migrate, combined, or report-only mode.
            overwrite_output: Explicit existing-output replacement permission.
            report_folder: Optional report location override.
            log_folder: Optional log location override.
            generate_log: Whether detailed Migration.log output is enabled.

        Returns:
            None.

        Raises:
            ValueError: If required values are blank or mode is unsupported.

        Notes:
            Defaults are sibling ``reports`` and ``logs`` folders beside the
            requested output GDB, not hard-coded machine paths.
        """
        if not all((configuration_folder, source_gdb, template_gdb, output_gdb)):
            raise ValueError("configuration_folder, source_gdb, template_gdb, and output_gdb are required.")
        if execution_mode not in EXECUTION_MODES:
            raise ValueError("Unsupported execution mode: {}".format(execution_mode))
        output_parent = Path(output_gdb).expanduser().parent
        self.configuration_folder = configuration_folder
        self.source_gdb = source_gdb
        self.template_gdb = template_gdb
        self.output_gdb = output_gdb
        self.execution_mode = execution_mode
        self.overwrite_output = overwrite_output
        self.report_folder = report_folder or str(output_parent / "reports")
        self.log_folder = log_folder or str(output_parent / "logs")
        self.generate_log = generate_log

    def run(self) -> ExecutionResult:
        """Execute the requested GMF lifecycle and return final typed status.

        Args:
            None.

        Returns:
            ExecutionResult containing phase outputs and final status.

        Raises:
            None.

        Notes:
            Expected framework exceptions are logged and converted to a final
            FAILED status.  The controller attempts CSV report generation for
            every outcome after logging begins.
        """
        logger: Optional[object] = None
        rule_set: Optional[RuleSet] = None
        validation_summary: Optional[ValidationSummary] = None
        migration_summary: Optional[MigrationSummary] = None
        report_paths: Optional[ReportPaths] = None
        audit_events: List[AuditEvent] = []
        status = ExecutionStatus.FAILED
        message = "Workflow did not start."

        try:
            logger = Logger(self.log_folder) if self.generate_log else _NullLogger()
            log_path = logger.initialize()
            self._log_start(logger)
            rule_set = self._load_configuration(logger, audit_events)

            if self.execution_mode in {MODE_VALIDATE_ONLY, MODE_VALIDATE_AND_MIGRATE}:
                validation_summary = self._validate(logger)
                audit_events.append(_validation_audit_event(validation_summary))
                if not validation_summary.passed:
                    status = ExecutionStatus.VALIDATION_FAILED
                    message = "Validation failed; template copying and migration were not started."
                    logger.error(message)
                    return self._finish(status, message, logger, validation_summary, migration_summary, rule_set, audit_events)

            if self.execution_mode in {MODE_MIGRATE_ONLY, MODE_VALIDATE_AND_MIGRATE}:
                logger.section("Copy template geodatabase")
                target_gdb = Migrator.prepare_output(self.template_gdb, self.output_gdb, self.overwrite_output)
                audit_events.append(AuditEvent("Template copy", "PASS", target_gdb, "Template geodatabase copied successfully."))
                logger.info("Template copied to {}.".format(target_gdb))

                logger.section("Migrate feature classes")
                migration_summary = Migrator(self.source_gdb, target_gdb, rule_set, logger).migrate()
                if migration_summary.success:
                    status = ExecutionStatus.SUCCESS
                    message = "Migration completed successfully."
                    audit_events.append(AuditEvent("Migration", "PASS", target_gdb, message))
                    logger.info(message)
                else:
                    status = ExecutionStatus.MIGRATION_FAILED
                    message = "Migration completed with feature-level failures."
                    audit_events.append(AuditEvent("Migration", "ERROR", target_gdb, message))
                    logger.error(message)
            elif self.execution_mode == MODE_VALIDATE_ONLY:
                status = ExecutionStatus.SUCCESS
                message = "Validation completed successfully."
                audit_events.append(AuditEvent("Validation workflow", "PASS", self.source_gdb, message))
                logger.info(message)
            elif self.execution_mode == MODE_GENERATE_REPORT:
                status = ExecutionStatus.SUCCESS
                message = "Configuration reports generated successfully."
                audit_events.append(AuditEvent("Report workflow", "PASS", self.configuration_folder, message))
                logger.info(message)

            return self._finish(status, message, logger, validation_summary, migration_summary, rule_set, audit_events)
        except Exception as error:
            status = ExecutionStatus.FAILED
            message = "GMF workflow failed: {}".format(error)
            audit_events.append(AuditEvent("Workflow", "ERROR", self.output_gdb, message))
            if logger is not None:
                logger.critical(message)
                logger.exception(error, "Main controller")
                try:
                    return self._finish(status, message, logger, validation_summary, migration_summary, rule_set, audit_events)
                except Exception as report_error:
                    logger.error("Final report generation failed: {}".format(report_error))
            return ExecutionResult(status, message, None, logger.log_path if logger else None, validation_summary, migration_summary, report_paths, tuple(audit_events))
        finally:
            if logger is not None:
                try:
                    logger.close()
                except Exception:
                    pass

    def _load_configuration(self, logger: object, audit_events: List[AuditEvent]) -> RuleSet:
        """Load typed configuration and record a workflow audit event.

        Args:
            logger: Initialized Logger.
            audit_events: Mutable workflow audit event list.

        Returns:
            Parsed typed RuleSet.

        Raises:
            ConfigurationError: If configuration cannot be loaded.

        Notes:
            Validator independently checks configuration again as part of its
            complete validation report; this first load is needed by migration.
        """
        logger.section("Load configuration")
        rule_set = load_configuration(self.configuration_folder)
        audit_events.append(AuditEvent("Configuration", "PASS", self.configuration_folder, "Typed configuration loaded."))
        logger.statistics(
            "Configuration statistics",
            {
                "Feature class rules": len(rule_set.feature_class_rules),
                "Field rules": len(rule_set.field_rules),
                "Domain rules": len(rule_set.domain_rules),
                "Lookup rules": len(rule_set.lookup_rules),
            },
        )
        return rule_set

    def _validate(self, logger: object) -> ValidationSummary:
        """Run preflight validation using the final report destination.

        Args:
            logger: Initialized Logger.

        Returns:
            Completed ValidationSummary.

        Raises:
            None.

        Notes:
            Validation errors remain result data rather than direct exceptions.
        """
        logger.section("Validate migration")
        summary = Validator(
            self.configuration_folder,
            self.source_gdb,
            self.template_gdb,
            self.report_folder,
            logger,
        ).validate()
        logger.statistics(
            "Validation statistics",
            {"Passed": summary.passed, "Warnings": summary.warning_count, "Errors": summary.error_count},
        )
        return summary

    def _finish(
        self,
        status: ExecutionStatus,
        message: str,
        logger: object,
        validation_summary: Optional[ValidationSummary],
        migration_summary: Optional[MigrationSummary],
        rule_set: Optional[RuleSet],
        audit_events: Sequence[AuditEvent],
    ) -> ExecutionResult:
        """Generate final reports and build the controller's result object.

        Args:
            status: Intended terminal status.
            message: Intended terminal message.
            logger: Initialized Logger.
            validation_summary: Optional validation output.
            migration_summary: Optional migration output.
            rule_set: Optional loaded configuration.
            audit_events: Workflow audit events.

        Returns:
            Complete ExecutionResult.

        Raises:
            Exception: Report generator errors are allowed to caller run's
                exception handler so final status accurately reflects failure.

        Notes:
            Report generation is deliberately centralized so every successful
            mode and validation failure emits the complete report set.
        """
        logger.section("Generate reports")
        report_paths = generate_reports(
            self.report_folder,
            validation_summary,
            migration_summary,
            rule_set,
            audit_events,
            logger,
        )
        logger.info("Reports generated in {}.".format(self.report_folder))
        return ExecutionResult(
            status,
            message,
            self.output_gdb if self.execution_mode in {MODE_MIGRATE_ONLY, MODE_VALIDATE_AND_MIGRATE} else None,
            logger.log_path,
            validation_summary,
            migration_summary,
            report_paths,
            tuple(audit_events),
        )

    def _log_start(self, logger: object) -> None:
        """Write workflow input values to the initialized migration log.

        Args:
            logger: Initialized Logger.

        Returns:
            None.

        Raises:
            None.

        Notes:
            No secrets or database connection details beyond supplied catalog
            paths are expanded or altered here.
        """
        logger.section("Geodatabase Migration Framework")
        logger.statistics(
            "Execution settings",
            {
                "Configuration folder": self.configuration_folder,
                "Source geodatabase": self.source_gdb,
                "Template geodatabase": self.template_gdb,
                "Output geodatabase": self.output_gdb,
                "Execution mode": self.execution_mode,
                "Overwrite output": self.overwrite_output,
            },
        )


def run(
    configuration_folder: str,
    source_gdb: str,
    template_gdb: str,
    output_gdb: str,
    execution_mode: str = MODE_VALIDATE_AND_MIGRATE,
    overwrite_output: bool = False,
    report_folder: Optional[str] = None,
    log_folder: Optional[str] = None,
    generate_log: bool = True,
) -> ExecutionResult:
    """Convenience function that executes the complete GMF controller.

    Args:
        configuration_folder: Folder containing required CSV configuration.
        source_gdb: Source geodatabase catalog path.
        template_gdb: Template geodatabase catalog path.
        output_gdb: Requested target geodatabase catalog path.
        execution_mode: Requested GMF execution mode.
        overwrite_output: Existing output replacement permission.
        report_folder: Optional report destination.
        log_folder: Optional Migration.log destination.
        generate_log: Whether detailed Migration.log output is enabled.

    Returns:
        Final ExecutionResult.

    Raises:
        ValueError: If controller inputs are invalid.

    Notes:
        Framework operational failures are represented by ExecutionStatus,
        allowing ArcGIS toolbox callers to display a concise final message.
    """
    return Transformer(
        configuration_folder, source_gdb, template_gdb, output_gdb,
        execution_mode, overwrite_output, report_folder, log_folder, generate_log,
    ).run()


def _validation_audit_event(summary: ValidationSummary) -> AuditEvent:
    """Build one audit event representing a completed validation phase.

    Args:
        summary: Completed validation summary.

    Returns:
        Typed AuditEvent.

    Raises:
        None.

    Notes:
        The detailed per-check results are supplied separately to report.py.
    """
    status = "PASS" if summary.passed else "ERROR"
    message = "Validation completed with {} warning(s) and {} error(s).".format(summary.warning_count, summary.error_count)
    return AuditEvent("Validation", status, summary.report_path, message)


__all__ = ["ExecutionResult", "ExecutionStatus", "Transformer", "run"]
