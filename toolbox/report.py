"""CSV report generation for the Geodatabase Migration Framework.

This module serializes typed validation, migration, and configuration data into
the eight CSV reports defined by GMF.  It does not execute validation or
migration and it does not create Excel workbooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

try:  # Supports package imports and ArcGIS Python-toolbox top-level imports.
    from .migrator import MigrationErrorRecord, MigrationSummary
    from .rules import DomainRule, FieldRule, RuleSet
    from .utils.constants import (
        AUDIT_REPORT_FILE, DOMAIN_REPORT_FILE, ERROR_REPORT_FILE,
        FEATURE_CLASS_REPORT_FILE, FIELD_REPORT_FILE,
        MIGRATION_SUMMARY_REPORT_FILE, VALIDATION_REPORT_FILE,
        WARNING_REPORT_FILE,
    )
    from .utils.exception_utils import ReportError
    from .utils.file_utils import ensure_folder, write_csv_rows
    from .validator import ValidationResult, ValidationStatus, ValidationSummary
except ImportError:  # pragma: no cover - exercised by ArcGIS toolbox loading.
    from migrator import MigrationErrorRecord, MigrationSummary  # type: ignore
    from rules import DomainRule, FieldRule, RuleSet  # type: ignore
    from utils.constants import (  # type: ignore
        AUDIT_REPORT_FILE, DOMAIN_REPORT_FILE, ERROR_REPORT_FILE,
        FEATURE_CLASS_REPORT_FILE, FIELD_REPORT_FILE,
        MIGRATION_SUMMARY_REPORT_FILE, VALIDATION_REPORT_FILE,
        WARNING_REPORT_FILE,
    )
    from utils.exception_utils import ReportError  # type: ignore
    from utils.file_utils import ensure_folder, write_csv_rows  # type: ignore
    from validator import ValidationResult, ValidationStatus, ValidationSummary  # type: ignore


_VALIDATION_FIELDS = ("Check", "Status", "Subject", "Message")
_MIGRATION_SUMMARY_FIELDS = (
    "Success", "FeatureClassMappings", "FeaturesRead", "FeaturesMigrated",
    "FeaturesSkipped", "FeaturesFailed", "ElapsedSeconds", "ErrorRecords",
)
_FEATURE_CLASS_FIELDS = (
    "SourceFeatureClass", "TargetFeatureClass", "Rule", "FeaturesRead",
    "FeaturesMigrated", "FeaturesSkipped", "FeaturesFailed", "ElapsedSeconds",
    "Success", "Messages",
)
_FIELD_FIELDS = (
    "Enabled", "SourceFeatureClass", "SourceField", "TargetFeatureClass",
    "TargetField", "Rule", "Parameter", "DefaultValue", "ConfigurationRow",
)
_DOMAIN_FIELDS = (
    "Enabled", "SourceFeatureClass", "SourceField", "SourceCode",
    "TargetFeatureClass", "TargetField", "TargetCode", "Description",
    "ConfigurationRow",
)
_ISSUE_FIELDS = ("Source", "Check", "Subject", "Message")
_AUDIT_FIELDS = ("Timestamp", "EventType", "Status", "Subject", "Message")


@dataclass(frozen=True)
class AuditEvent:
    """Optional caller-supplied event for Audit_Report.csv.

    Args:
        event_type: Concise event category.
        status: PASS, WARNING, ERROR, or another caller-defined status.
        subject: Related GDB path, feature class, or operation.
        message: Auditable event text.

    Raises:
        None.

    Notes:
        ReportGenerator adds standard validation and migration events itself.
    """

    event_type: str
    status: str
    subject: str
    message: str


@dataclass(frozen=True)
class ReportPaths:
    """Absolute file paths for all generated GMF CSV reports.

    Args:
        validation_report: Validation_Report.csv path.
        migration_summary_report: Migration_Summary.csv path.
        feature_class_report: FeatureClass_Report.csv path.
        field_report: Field_Report.csv path.
        domain_report: Domain_Report.csv path.
        warning_report: Warning_Report.csv path.
        error_report: Error_Report.csv path.
        audit_report: Audit_Report.csv path.

    Raises:
        None.

    Notes:
        Every requested report is generated, even if it contains only a header.
    """

    validation_report: str
    migration_summary_report: str
    feature_class_report: str
    field_report: str
    domain_report: str
    warning_report: str
    error_report: str
    audit_report: str


class ReportGenerator:
    """Generate all required GMF CSV reports from typed framework data.

    Args:
        report_folder: Destination folder for the eight CSV reports.
        logger: Optional Logger-compatible object for report messages.

    Raises:
        ValueError: If report_folder is empty.

    Notes:
        The generator is intentionally independent of ArcPy and can be tested
        using constructed ValidationSummary and MigrationSummary objects.
    """

    def __init__(self, report_folder: str, logger: Optional[object] = None) -> None:
        """Create a report generator without writing files.

        Args:
            report_folder: Folder for all report CSV files.
            logger: Optional framework logger.

        Returns:
            None.

        Raises:
            ValueError: If report_folder is blank.

        Notes:
            The folder is created when generate is called.
        """
        if not report_folder:
            raise ValueError("report_folder is required.")
        self.report_folder = report_folder
        self.logger = logger

    def generate(
        self,
        validation_summary: Optional[ValidationSummary] = None,
        migration_summary: Optional[MigrationSummary] = None,
        rule_set: Optional[RuleSet] = None,
        audit_events: Sequence[AuditEvent] = (),
    ) -> ReportPaths:
        """Generate all eight required GMF CSV reports.

        Args:
            validation_summary: Optional completed validation results.
            migration_summary: Optional completed migration statistics.
            rule_set: Optional typed configuration rules.
            audit_events: Optional additional audit events.

        Returns:
            Paths to every created report file.

        Raises:
            ReportError: If report output cannot be created or written.

        Notes:
            Missing inputs produce header-only reports rather than suppressing
            required report artifacts.
        """
        try:
            folder = ensure_folder(self.report_folder)
            validation_rows = _validation_rows(validation_summary)
            migration_rows = _migration_summary_rows(migration_summary)
            feature_rows = _feature_class_rows(migration_summary)
            field_rows = _field_rows(rule_set)
            domain_rows = _domain_rows(rule_set)
            warning_rows = _warning_rows(validation_summary)
            error_rows = _error_rows(validation_summary, migration_summary)
            audit_rows = _audit_rows(validation_summary, migration_summary, audit_events)

            paths = ReportPaths(
                validation_report=str(write_csv_rows(folder / VALIDATION_REPORT_FILE, _VALIDATION_FIELDS, validation_rows)),
                migration_summary_report=str(write_csv_rows(folder / MIGRATION_SUMMARY_REPORT_FILE, _MIGRATION_SUMMARY_FIELDS, migration_rows)),
                feature_class_report=str(write_csv_rows(folder / FEATURE_CLASS_REPORT_FILE, _FEATURE_CLASS_FIELDS, feature_rows)),
                field_report=str(write_csv_rows(folder / FIELD_REPORT_FILE, _FIELD_FIELDS, field_rows)),
                domain_report=str(write_csv_rows(folder / DOMAIN_REPORT_FILE, _DOMAIN_FIELDS, domain_rows)),
                warning_report=str(write_csv_rows(folder / WARNING_REPORT_FILE, _ISSUE_FIELDS, warning_rows)),
                error_report=str(write_csv_rows(folder / ERROR_REPORT_FILE, _ISSUE_FIELDS, error_rows)),
                audit_report=str(write_csv_rows(folder / AUDIT_REPORT_FILE, _AUDIT_FIELDS, audit_rows)),
            )
        except Exception as error:
            raise ReportError("Unable to generate GMF CSV reports: {}".format(error)) from error
        self._log("info", "Generated GMF CSV reports in {}.".format(folder))
        return paths

    def _log(self, level: str, message: str) -> None:
        """Send a report-generation message to an optional Logger.

        Args:
            level: Logger method name.
            message: Report message.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Reporting output is not made to fail solely due to logging failure.
        """
        if self.logger is None:
            return
        try:
            getattr(self.logger, level)(message)
        except Exception:
            pass


def generate_reports(
    report_folder: str,
    validation_summary: Optional[ValidationSummary] = None,
    migration_summary: Optional[MigrationSummary] = None,
    rule_set: Optional[RuleSet] = None,
    audit_events: Sequence[AuditEvent] = (),
    logger: Optional[object] = None,
) -> ReportPaths:
    """Convenience function for generating all required GMF CSV reports.

    Args:
        report_folder: Destination folder for report files.
        validation_summary: Optional validation output.
        migration_summary: Optional migration output.
        rule_set: Optional typed rules.
        audit_events: Optional caller-supplied audit records.
        logger: Optional framework logger.

    Returns:
        Paths to all generated CSV reports.

    Raises:
        ReportError: If any CSV cannot be written.

    Notes:
        This is the simple orchestration entry point for transformer.py.
    """
    return ReportGenerator(report_folder, logger).generate(validation_summary, migration_summary, rule_set, audit_events)


def _validation_rows(summary: Optional[ValidationSummary]) -> List[Mapping[str, object]]:
    """Convert typed validation results into Validation_Report rows.

    Args:
        summary: Optional validation summary.

    Returns:
        CSV row mappings in validation order.

    Raises:
        None.

    Notes:
        Validator may already have written this report; report generation
        rewrites it consistently alongside the other artifacts.
    """
    if summary is None:
        return []
    return [
        {"Check": item.check, "Status": item.status.value, "Subject": item.subject, "Message": item.message}
        for item in summary.results
    ]


def _migration_summary_rows(summary: Optional[MigrationSummary]) -> List[Mapping[str, object]]:
    """Convert aggregate migration metrics into one summary CSV row.

    Args:
        summary: Optional migration summary.

    Returns:
        One CSV row or an empty list.

    Raises:
        None.

    Notes:
        A header-only report accurately represents a validation-only run.
    """
    if summary is None:
        return []
    return [{
        "Success": summary.success, "FeatureClassMappings": summary.mapping_count,
        "FeaturesRead": summary.features_read, "FeaturesMigrated": summary.features_migrated,
        "FeaturesSkipped": summary.features_skipped, "FeaturesFailed": summary.features_failed,
        "ElapsedSeconds": summary.elapsed_seconds, "ErrorRecords": len(summary.error_records),
    }]


def _feature_class_rows(summary: Optional[MigrationSummary]) -> List[Mapping[str, object]]:
    """Convert per-mapping statistics into FeatureClass_Report rows.

    Args:
        summary: Optional migration summary.

    Returns:
        Per-feature-class CSV row mappings.

    Raises:
        None.

    Notes:
        Message lists are joined with a line-feed-safe separator for CSV.
    """
    if summary is None:
        return []
    return [{
        "SourceFeatureClass": item.source_feature_class,
        "TargetFeatureClass": item.target_feature_class,
        "Rule": item.rule_name,
        "FeaturesRead": item.features_read,
        "FeaturesMigrated": item.features_migrated,
        "FeaturesSkipped": item.features_skipped,
        "FeaturesFailed": item.features_failed,
        "ElapsedSeconds": item.elapsed_seconds,
        "Success": item.success,
        "Messages": " | ".join(item.messages),
    } for item in summary.feature_class_statistics]


def _field_rows(rule_set: Optional[RuleSet]) -> List[Mapping[str, object]]:
    """Convert typed FieldRule instances into Field_Report rows.

    Args:
        rule_set: Optional typed configuration rules.

    Returns:
        Field mapping CSV row mappings.

    Raises:
        None.

    Notes:
        This is a configuration audit report, not a per-row transformation log.
    """
    if rule_set is None:
        return []
    return [_field_row(rule) for rule in rule_set.field_rules]


def _field_row(rule: FieldRule) -> Mapping[str, object]:
    """Convert one FieldRule into a stable report row.

    Args:
        rule: Typed field mapping rule.

    Returns:
        Field report row mapping.

    Raises:
        None.

    Notes:
        Optional source/default/parameter values remain blank when absent.
    """
    return {
        "Enabled": rule.enabled, "SourceFeatureClass": rule.source_feature_class,
        "SourceField": rule.source_field or "", "TargetFeatureClass": rule.target_feature_class,
        "TargetField": rule.target_field, "Rule": rule.rule.value,
        "Parameter": rule.parameter or "", "DefaultValue": rule.default_value or "",
        "ConfigurationRow": rule.row_number,
    }


def _domain_rows(rule_set: Optional[RuleSet]) -> List[Mapping[str, object]]:
    """Convert typed DomainRule instances into Domain_Report rows.

    Args:
        rule_set: Optional typed configuration rules.

    Returns:
        Domain mapping CSV row mappings.

    Raises:
        None.

    Notes:
        Domain report records configuration values only; no domain is edited.
    """
    if rule_set is None:
        return []
    return [_domain_row(rule) for rule in rule_set.domain_rules]


def _domain_row(rule: DomainRule) -> Mapping[str, object]:
    """Convert one DomainRule into a stable report row.

    Args:
        rule: Typed domain mapping rule.

    Returns:
        Domain report row mapping.

    Raises:
        None.

    Notes:
        Code strings retain leading zeros from CSV configuration.
    """
    return {
        "Enabled": rule.enabled, "SourceFeatureClass": rule.source_feature_class,
        "SourceField": rule.source_field, "SourceCode": rule.source_code,
        "TargetFeatureClass": rule.target_feature_class, "TargetField": rule.target_field,
        "TargetCode": rule.target_code, "Description": rule.description or "",
        "ConfigurationRow": rule.row_number,
    }


def _warning_rows(summary: Optional[ValidationSummary]) -> List[Mapping[str, object]]:
    """Return validation warnings for Warning_Report.csv.

    Args:
        summary: Optional validation summary.

    Returns:
        Warning report rows.

    Raises:
        None.

    Notes:
        Migration warnings can be passed as explicit AuditEvent records.
    """
    return _validation_issue_rows(summary, ValidationStatus.WARNING)


def _error_rows(validation: Optional[ValidationSummary], migration: Optional[MigrationSummary]) -> List[Mapping[str, object]]:
    """Return validation and migration errors for Error_Report.csv.

    Args:
        validation: Optional validation summary.
        migration: Optional migration summary.

    Returns:
        Error report rows.

    Raises:
        None.

    Notes:
        Every retained row-level MigrationErrorRecord becomes one CSV row.
    """
    rows: List[Mapping[str, object]] = _validation_issue_rows(validation, ValidationStatus.ERROR)
    if migration is not None:
        rows.extend(_migration_error_row(error) for error in migration.error_records)
    return rows


def _validation_issue_rows(summary: Optional[ValidationSummary], status: ValidationStatus) -> List[Mapping[str, object]]:
    """Filter typed validation results by a requested issue status.

    Args:
        summary: Optional validation summary.
        status: Requested WARNING or ERROR status.

    Returns:
        Matching issue row mappings.

    Raises:
        None.

    Notes:
        PASS results belong only in Validation_Report.csv and Audit_Report.csv.
    """
    if summary is None:
        return []
    return [
        {"Source": "Validation", "Check": item.check, "Subject": item.subject, "Message": item.message}
        for item in summary.results if item.status is status
    ]


def _migration_error_row(error: MigrationErrorRecord) -> Mapping[str, object]:
    """Convert one migration audit error into Error_Report format.

    Args:
        error: Retained migration failure record.

    Returns:
        Error report row mapping.

    Raises:
        None.

    Notes:
        Source row numbers are embedded in Check for concise CSV structure.
    """
    row_label = "Feature row {}".format(error.source_row_number) if error.source_row_number else "Feature class mapping"
    return {
        "Source": "Migration", "Check": row_label,
        "Subject": "{} -> {}".format(error.source_feature_class, error.target_feature_class),
        "Message": error.message,
    }


def _audit_rows(
    validation: Optional[ValidationSummary],
    migration: Optional[MigrationSummary],
    events: Sequence[AuditEvent],
) -> List[Mapping[str, object]]:
    """Build complete audit rows from validation, migration, and caller events.

    Args:
        validation: Optional validation summary.
        migration: Optional migration summary.
        events: Caller-provided audit events.

    Returns:
        Ordered audit-report row mappings.

    Raises:
        None.

    Notes:
        One timestamp is used for report generation to make the audit coherent.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows: List[Mapping[str, object]] = []
    if validation is not None:
        rows.extend({
            "Timestamp": timestamp, "EventType": "Validation", "Status": item.status.value,
            "Subject": item.subject, "Message": "{}: {}".format(item.check, item.message),
        } for item in validation.results)
    if migration is not None:
        rows.append({
            "Timestamp": timestamp, "EventType": "Migration summary",
            "Status": "PASS" if migration.success else "ERROR", "Subject": "",
            "Message": "{} migrated, {} failed, {} skipped in {} seconds.".format(
                migration.features_migrated, migration.features_failed,
                migration.features_skipped, migration.elapsed_seconds,
            ),
        })
        rows.extend({
            "Timestamp": timestamp, "EventType": "Migration error", "Status": "ERROR",
            "Subject": "{} -> {}".format(error.source_feature_class, error.target_feature_class),
            "Message": error.message,
        } for error in migration.error_records)
    rows.extend({
        "Timestamp": timestamp, "EventType": event.event_type, "Status": event.status,
        "Subject": event.subject, "Message": event.message,
    } for event in events)
    return rows


__all__ = ["AuditEvent", "ReportGenerator", "ReportPaths", "generate_reports"]
