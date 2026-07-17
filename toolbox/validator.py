"""Validation service for Geodatabase Migration Framework configurations.

The validator performs read-only preflight checks for a configured migration.
It never creates or alters geodatabase schema, and it writes the required
``Validation_Report.csv`` after every validation attempt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:  # Supports package imports and ArcGIS Python-toolbox top-level imports.
    from . import rules
    from .rules import (
        DomainRule, FeatureClassRule, FieldRule, FieldRuleName,
        GeometryRuleName, LookupColumnRule, LookupRule, RuleSet,
    )
    from .utils import gdb_utils
    from .utils.arcpy_utils import search_cursor
    from .utils.constants import VALIDATION_REPORT_FILE
    from .utils.exception_utils import ConfigurationError, ReportError
    from .utils.file_utils import ensure_folder, write_csv_rows
except ImportError:  # pragma: no cover - exercised by ArcGIS toolbox loading.
    import rules  # type: ignore
    from rules import (  # type: ignore
        DomainRule, FeatureClassRule, FieldRule, FieldRuleName,
        GeometryRuleName, LookupColumnRule, LookupRule, RuleSet,
    )
    from utils import gdb_utils  # type: ignore
    from utils.arcpy_utils import search_cursor  # type: ignore
    from utils.constants import VALIDATION_REPORT_FILE  # type: ignore
    from utils.exception_utils import ConfigurationError, ReportError  # type: ignore
    from utils.file_utils import ensure_folder, write_csv_rows  # type: ignore


class ValidationStatus(str, Enum):
    """Possible outcomes for one validation check."""

    PASS = "PASS"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ValidationResult:
    """One immutable, reportable validation result.

    Args:
        check: Name of the validation check.
        status: PASS, WARNING, or ERROR outcome.
        message: Human-readable diagnostic.
        subject: Optional path, rule, or object being checked.

    Raises:
        None.

    Notes:
        Results are retained in order so the CSV mirrors validation execution.
    """

    check: str
    status: ValidationStatus
    message: str
    subject: str = ""


@dataclass(frozen=True)
class ValidationSummary:
    """Immutable result collection for one validation run.

    Args:
        results: Ordered validation results.
        report_path: Created Validation_Report.csv path.

    Raises:
        None.

    Notes:
        A summary is successful only when it contains no ERROR results.
    """

    results: Tuple[ValidationResult, ...]
    report_path: str

    @property
    def passed(self) -> bool:
        """Return whether no validation result has ERROR status.

        Args:
            None.

        Returns:
            ``True`` when validation completed without errors.

        Raises:
            None.

        Notes:
            Warnings do not prevent migration but should be reviewed.
        """
        return not any(result.status is ValidationStatus.ERROR for result in self.results)

    @property
    def error_count(self) -> int:
        """Return the number of ERROR results.

        Args:
            None.

        Returns:
            Error result count.

        Raises:
            None.

        Notes:
            This is useful to drive toolbox messages and execution decisions.
        """
        return sum(result.status is ValidationStatus.ERROR for result in self.results)

    @property
    def warning_count(self) -> int:
        """Return the number of WARNING results.

        Args:
            None.

        Returns:
            Warning result count.

        Raises:
            None.

        Notes:
            Warnings do not make the summary fail.
        """
        return sum(result.status is ValidationStatus.WARNING for result in self.results)


class Validator:
    """Run read-only GMF preflight checks and write Validation_Report.csv.

    Args:
        configuration_folder: Folder containing the four required CSV files.
        source_gdb: Source geodatabase catalog path.
        template_gdb: Template geodatabase catalog path.
        report_folder: Optional report destination. Defaults to ``reports`` in
            the configuration folder.
        logger: Optional Logger-compatible object with info/warning/error.

    Raises:
        ValueError: If a required constructor path is empty.

    Notes:
        Validation errors are accumulated into results.  Only an inability to
        write Validation_Report.csv raises a ReportError.
    """

    def __init__(
        self,
        configuration_folder: str,
        source_gdb: str,
        template_gdb: str,
        report_folder: Optional[str] = None,
        logger: Optional[object] = None,
    ) -> None:
        """Create a Validator with explicit configuration and GDB locations.

        Args:
            configuration_folder: Required CSV configuration folder.
            source_gdb: Source geodatabase to inspect.
            template_gdb: Target template geodatabase to inspect.
            report_folder: Optional report folder override.
            logger: Optional framework logger.

        Returns:
            None.

        Raises:
            ValueError: If any required path is blank.

        Notes:
            The report destination is created only when validation runs.
        """
        if not configuration_folder or not source_gdb or not template_gdb:
            raise ValueError("configuration_folder, source_gdb, and template_gdb are required.")
        self.configuration_folder = str(Path(configuration_folder).expanduser())
        self.source_gdb = source_gdb
        self.template_gdb = template_gdb
        self.report_folder = report_folder or str(Path(self.configuration_folder) / "reports")
        self.logger = logger
        self._results: List[ValidationResult] = []
        self._cache = gdb_utils.MetadataCache()
        self._field_exists_cache: Dict[Tuple[str, str], bool] = {}
        self._field_information_cache: Dict[str, Dict[str, Dict[str, object]]] = {}

    def validate(self) -> ValidationSummary:
        """Run all configured checks and write Validation_Report.csv.

        Args:
            None.

        Returns:
            ValidationSummary containing every result and report path.

        Raises:
            ReportError: If Validation_Report.csv cannot be written.

        Notes:
            Configuration, workspace, rule, geometry, spatial-reference,
            field, domain, lookup, and SQL-filter checks are all attempted
            whenever their dependencies are available.
        """
        self._results = []
        self._cache.clear()
        self._field_exists_cache.clear()
        self._field_information_cache.clear()
        rule_set = self._validate_configuration()
        source_valid = self._validate_workspace(self.source_gdb, "Source geodatabase")
        template_valid = self._validate_workspace(self.template_gdb, "Template geodatabase")

        if rule_set is not None:
            self._validate_lookup(rule_set)
        if rule_set is not None and source_valid and template_valid:
            source_paths, target_paths = self._validate_feature_classes(rule_set)
            self._validate_geometry_and_spatial_reference(rule_set, source_paths, target_paths)
            self._validate_fields(rule_set, source_paths, target_paths)
            self._validate_domains(rule_set, source_paths, target_paths)
            self._validate_sql_filters(rule_set, source_paths)
        elif rule_set is not None:
            self._add(
                "Dependent checks", ValidationStatus.WARNING,
                "Feature-class, geometry, field, domain, lookup, and SQL checks were skipped because one or both geodatabases are invalid.",
            )

        report_path = self._write_report()
        return ValidationSummary(tuple(self._results), report_path)

    def _validate_configuration(self) -> Optional[RuleSet]:
        """Load configuration rules and record a result rather than raising.

        Args:
            None.

        Returns:
            Parsed RuleSet, or None if configuration is invalid.

        Raises:
            None.

        Notes:
            The typed rules loader validates all mandatory CSV columns.
        """
        try:
            rule_set = rules.load_configuration(self.configuration_folder)
        except ConfigurationError as error:
            self._add("Configuration", ValidationStatus.ERROR, str(error), self.configuration_folder)
            return None
        self._add("Configuration", ValidationStatus.PASS, "All required configuration CSV files and mandatory columns are valid.", self.configuration_folder)
        return rule_set

    def _validate_workspace(self, workspace: str, label: str) -> bool:
        """Validate a source or template geodatabase and record its result.

        Args:
            workspace: Geodatabase catalog path.
            label: Human-readable workspace label.

        Returns:
            ``True`` when the workspace is a valid geodatabase.

        Raises:
            None.

        Notes:
            Raw ArcPy errors are converted to validation results by utilities.
        """
        try:
            gdb_utils.validate_geodatabase(workspace, label)
        except Exception as error:
            self._add(label, ValidationStatus.ERROR, str(error), workspace)
            return False
        self._add(label, ValidationStatus.PASS, "Workspace exists and is a supported geodatabase.", workspace)
        return True

    def _validate_feature_classes(self, rule_set: RuleSet) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Validate all enabled source and target feature-class mappings.

        Args:
            rule_set: Parsed migration rules.

        Returns:
            Case-normalized source and target feature-class path maps.

        Raises:
            None.

        Notes:
            Each feature class is checked against supported V1 geometry types.
        """
        source_paths: Dict[str, str] = {}
        target_paths: Dict[str, str] = {}
        for rule in _enabled(rule_set.feature_class_rules):
            source_path = gdb_utils.feature_class_path(self.source_gdb, rule.source_dataset, rule.source_feature_class)
            source_paths.setdefault(rule.source_feature_class.casefold(), source_path)
            if rule.target_feature_class:
                target_path = gdb_utils.feature_class_path(self.template_gdb, rule.target_dataset, rule.target_feature_class)
                target_paths.setdefault(rule.target_feature_class.casefold(), target_path)
            self._validate_feature_class(source_path, "Source feature class", rule.row_number)
            if rule.target_feature_class:
                self._validate_feature_class(target_path, "Target feature class", rule.row_number)
        if not source_paths:
            self._add("Feature classes", ValidationStatus.WARNING, "No enabled feature-class mapping rules were found.")
        return source_paths, target_paths

    def _validate_feature_class(self, path: str, label: str, row_number: int) -> None:
        """Validate one feature class and append a detailed result.

        Args:
            path: Feature class catalog path.
            label: Source or target label.
            row_number: Mapping CSV row number.

        Returns:
            None.

        Raises:
            None.

        Notes:
            The metadata cache prevents repeated Describe calls in later checks.
        """
        try:
            description = gdb_utils.validate_feature_class(path, self._cache)
            geometry = getattr(description, "shapeType", "Unknown")
            self._add(label, ValidationStatus.PASS, "FC_Mapping.csv row {} is a supported {} feature class.".format(row_number, geometry), path)
        except Exception as error:
            self._add(label, ValidationStatus.ERROR, "FC_Mapping.csv row {}: {}".format(row_number, error), path)

    def _validate_geometry_and_spatial_reference(
        self,
        rule_set: RuleSet,
        source_paths: Mapping[str, str],
        target_paths: Mapping[str, str],
    ) -> None:
        """Validate geometry-rule compatibility and spatial-reference expectations.

        Args:
            rule_set: Parsed feature-class rules.
            source_paths: Resolved source path map.
            target_paths: Resolved target path map.

        Returns:
            None.

        Raises:
            None.

        Notes:
            PROJECT may legitimately use different coordinate systems; all other
            geometry rules require matching spatial references.
        """
        for rule in _enabled(rule_set.feature_class_rules):
            source_path = source_paths.get(rule.source_feature_class.casefold())
            target_path = target_paths.get(rule.target_feature_class.casefold())
            if not source_path or not target_path:
                continue
            try:
                source_info = gdb_utils.feature_class_information(source_path, self._cache)
                target_info = gdb_utils.feature_class_information(target_path, self._cache)
            except Exception:
                continue  # Feature-class errors already identify the failure.
            self._validate_geometry_rule(rule, source_info.geometry_type, target_info.geometry_type, source_path, target_path)
            self._validate_spatial_reference(rule, source_info, target_info, target_path)

    def _validate_geometry_rule(
        self,
        rule: FeatureClassRule,
        source_geometry: str,
        target_geometry: str,
        source_path: str,
        target_path: str,
    ) -> None:
        """Record whether a geometry transformation can produce target geometry.

        Args:
            rule: Feature-class mapping rule.
            source_geometry: Source ArcGIS shape type.
            target_geometry: Target ArcGIS shape type.
            source_path: Source feature-class path.
            target_path: Target feature-class path.

        Returns:
            None.

        Raises:
            None.

        Notes:
            BUFFER output is Polygon; CENTROID output is Point; BOUNDARY output
            is Polyline for polygons and Point for linear source features.
        """
        expected = _expected_geometry(rule.geometry_rule, source_geometry)
        subject = "{} -> {}".format(source_path, target_path)
        if expected is None or expected == target_geometry:
            self._add("Geometry", ValidationStatus.PASS, "FC_Mapping.csv row {} geometry rule {} is compatible ({} -> {}).".format(rule.row_number, rule.geometry_rule.value, source_geometry, target_geometry), subject)
        else:
            self._add("Geometry", ValidationStatus.ERROR, "FC_Mapping.csv row {} geometry rule {} expects target {} but target is {}.".format(rule.row_number, rule.geometry_rule.value, expected, target_geometry), subject)

    def _validate_spatial_reference(self, rule: FeatureClassRule, source_info: object, target_info: object, subject: str) -> None:
        """Validate source/target spatial references for a feature-class rule.

        Args:
            rule: Feature-class mapping rule.
            source_info: Source FeatureClassInfo.
            target_info: Target FeatureClassInfo.
            subject: Target feature-class path.

        Returns:
            None.

        Raises:
            None.

        Notes:
            PROJECT intentionally permits unequal coordinate systems.
        """
        source_code = getattr(source_info, "spatial_reference_factory_code")
        target_code = getattr(target_info, "spatial_reference_factory_code")
        source_name = getattr(source_info, "spatial_reference_name")
        target_name = getattr(target_info, "spatial_reference_name")
        same_reference = source_code == target_code if source_code is not None and target_code is not None else source_name == target_name
        if rule.geometry_rule is GeometryRuleName.PROJECT:
            self._add("Spatial reference", ValidationStatus.PASS, "FC_Mapping.csv row {} uses PROJECT; source {} may be transformed to target {}.".format(rule.row_number, source_name, target_name), subject)
        elif same_reference:
            self._add("Spatial reference", ValidationStatus.PASS, "FC_Mapping.csv row {} spatial references match ({}).".format(rule.row_number, source_name), subject)
        else:
            self._add("Spatial reference", ValidationStatus.ERROR, "FC_Mapping.csv row {} requires matching spatial references; source is {} and target is {}.".format(rule.row_number, source_name, target_name), subject)

    def _validate_fields(self, rule_set: RuleSet, source_paths: Mapping[str, str], target_paths: Mapping[str, str]) -> None:
        """Validate source and target fields referenced by enabled field rules.

        Args:
            rule_set: Parsed field rules.
            source_paths: Resolved source path map.
            target_paths: Resolved target path map.

        Returns:
            None.

        Raises:
            None.

        Notes:
            DEFAULT, UUID, and IGNORE need no source field; every rule requires
            the target field to already exist in the template schema.
        """
        for rule in _enabled(rule_set.field_rules):
            source_path = _resolve_path(source_paths, self.source_gdb, rule.source_feature_class)
            target_path = _resolve_path(target_paths, self.template_gdb, rule.target_feature_class)
            if rule.source_field and rule.rule not in {FieldRuleName.DEFAULT, FieldRuleName.UUID, FieldRuleName.IGNORE}:
                self._validate_field(source_path, rule.source_field, "Source field", rule.row_number)
            self._validate_field(target_path, rule.target_field, "Target field", rule.row_number)

    def _validate_field(self, feature_class: str, field_name: str, label: str, row_number: int) -> None:
        """Record a single feature-class field existence check.

        Args:
            feature_class: Feature class containing the expected field.
            field_name: Expected field name.
            label: Source or target label.
            row_number: Field mapping CSV row number.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Field matching is case-insensitive through gdb_utils.field_exists.
        """
        try:
            cache_key = (feature_class.casefold(), field_name.casefold())
            if cache_key not in self._field_exists_cache:
                self._field_exists_cache[cache_key] = gdb_utils.field_exists(
                    feature_class,
                    field_name,
                )
            exists = self._field_exists_cache[cache_key]
        except Exception as error:
            self._add(label, ValidationStatus.ERROR, "Field_Mapping.csv row {}: cannot inspect {}: {}".format(row_number, field_name, error), feature_class)
        else:
            status = ValidationStatus.PASS if exists else ValidationStatus.ERROR
            message = "Field_Mapping.csv row {} {} {}.".format(row_number, "contains" if exists else "does not contain", field_name)
            self._add(label, status, message, feature_class)

    def _validate_domains(self, rule_set: RuleSet, source_paths: Mapping[str, str], target_paths: Mapping[str, str]) -> None:
        """Validate configured target domains and domain mapping field references.

        Args:
            rule_set: Parsed field and domain rules.
            source_paths: Resolved source path map.
            target_paths: Resolved target path map.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Domains are read only.  No target domains or fields are modified.
        """
        try:
            template_domains = gdb_utils.domain_information(self.template_gdb)
        except Exception as error:
            self._add("Domains", ValidationStatus.ERROR, "Cannot inspect template domains: {}".format(error), self.template_gdb)
            return
        domain_names = {name.casefold() for name in template_domains}
        for field_rule in _enabled(rule_set.field_rules):
            if field_rule.rule is FieldRuleName.DOMAIN:
                if not field_rule.parameter:
                    self._add("Domains", ValidationStatus.ERROR, "Field_Mapping.csv row {} DOMAIN rule requires Parameter domain name.".format(field_rule.row_number))
                elif field_rule.parameter.casefold() in domain_names:
                    self._add("Domains", ValidationStatus.PASS, "Field_Mapping.csv row {} references existing template domain {}.".format(field_rule.row_number, field_rule.parameter), self.template_gdb)
                else:
                    self._add("Domains", ValidationStatus.ERROR, "Field_Mapping.csv row {} references missing template domain {}.".format(field_rule.row_number, field_rule.parameter), self.template_gdb)
        for domain_rule in _enabled(rule_set.domain_rules):
            source_path = _resolve_path(source_paths, self.source_gdb, domain_rule.source_feature_class)
            target_path = _resolve_path(target_paths, self.template_gdb, domain_rule.target_feature_class)
            self._validate_field(source_path, domain_rule.source_field, "Domain source field", domain_rule.row_number)
            self._validate_field(target_path, domain_rule.target_field, "Domain target field", domain_rule.row_number)
            self._validate_domain_code(template_domains, target_path, domain_rule)

    def _validate_domain_code(self, domains: Mapping[str, Mapping[str, object]], target_path: str, rule: DomainRule) -> None:
        """Validate a target code when the target field has a coded-value domain.

        Args:
            domains: Existing template-domain metadata.
            target_path: Target feature-class path.
            rule: Domain mapping rule.

        Returns:
            None.

        Raises:
            None.

        Notes:
            An unassigned target field is reported as a warning because a
            domain-mapping CSV may be used to normalize values before insert.
        """
        try:
            fields = self._field_information_cache.get(target_path)
            if fields is None:
                fields = gdb_utils.field_information(target_path)
                self._field_information_cache[target_path] = fields
            field = _field_metadata(fields, rule.target_field)
        except Exception:
            return
        domain_name = str(field.get("domain") or "") if field else ""
        if not domain_name:
            self._add("Domain code", ValidationStatus.WARNING, "Domain_Mapping.csv row {} target field {} has no assigned domain.".format(rule.row_number, rule.target_field), target_path)
            return
        domain = next((value for name, value in domains.items() if name.casefold() == domain_name.casefold()), None)
        coded_values = domain.get("coded_values", {}) if domain else {}
        if coded_values and rule.target_code not in {str(code) for code in coded_values}:
            self._add("Domain code", ValidationStatus.ERROR, "Domain_Mapping.csv row {} target code {} is not in domain {}.".format(rule.row_number, rule.target_code, domain_name), target_path)
        else:
            self._add("Domain code", ValidationStatus.PASS, "Domain_Mapping.csv row {} target code {} is valid for {}.".format(rule.row_number, rule.target_code, domain_name), target_path)

    def _validate_lookup(self, rule_set: RuleSet) -> None:
        """Validate lookup schema definitions and LOOKUP field rule references.

        Args:
            rule_set: Parsed lookup and field rules.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Both lookup value-map and AMRUT definition-manifest formats are
            supported by the typed rules loader.
        """
        value_rules = [rule for rule in rule_set.lookup_rules if isinstance(rule, LookupRule)]
        definition_rules = [rule for rule in rule_set.lookup_rules if isinstance(rule, LookupColumnRule)]
        if definition_rules:
            names = [rule.column_name.casefold() for rule in definition_rules]
            duplicates = {name for name in names if names.count(name) > 1}
            required_names = {rule.column_name.casefold() for rule in definition_rules if rule.required}
            missing = {name.casefold() for name in ("Lookup_Name", "Source_Value", "Target_Value")} - required_names
            if duplicates:
                self._add("Lookup", ValidationStatus.ERROR, "Lookup.csv contains duplicate column definition(s): {}.".format(", ".join(sorted(duplicates))))
            elif missing:
                self._add("Lookup", ValidationStatus.ERROR, "Lookup.csv definition is missing required column(s): {}.".format(", ".join(sorted(missing))))
            else:
                self._add("Lookup", ValidationStatus.PASS, "Lookup.csv column definition contains all required lookup columns.")
        elif value_rules:
            duplicate_keys = _duplicate_lookup_keys(value_rules)
            if duplicate_keys:
                self._add("Lookup", ValidationStatus.ERROR, "Lookup.csv has duplicate lookup-name/source-value pairs: {}.".format(", ".join(duplicate_keys)))
            else:
                self._add("Lookup", ValidationStatus.PASS, "Lookup.csv value mappings are unique and valid.")
        else:
            self._add("Lookup", ValidationStatus.WARNING, "Lookup.csv contains no lookup rules.")
        for field_rule in _enabled(rule_set.field_rules):
            if field_rule.rule is FieldRuleName.LOOKUP and not field_rule.parameter:
                self._add("Lookup", ValidationStatus.ERROR, "Field_Mapping.csv row {} LOOKUP rule requires Parameter lookup name.".format(field_rule.row_number))

    def _validate_sql_filters(self, rule_set: RuleSet, source_paths: Mapping[str, str]) -> None:
        """Validate SQL filters by opening a read-only SearchCursor.

        Args:
            rule_set: Parsed feature-class rules.
            source_paths: Resolved source path map.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Opening the cursor validates the SQL expression without reading or
            changing any source feature rows.
        """
        for rule in _enabled(rule_set.feature_class_rules):
            if not rule.sql_filter:
                self._add("SQL filter", ValidationStatus.PASS, "FC_Mapping.csv row {} has no SQL filter.".format(rule.row_number))
                continue
            source_path = source_paths.get(rule.source_feature_class.casefold())
            if not source_path:
                continue
            try:
                with search_cursor(source_path, ["OID@"], rule.sql_filter):
                    pass
            except Exception as error:
                self._add("SQL filter", ValidationStatus.ERROR, "FC_Mapping.csv row {} has invalid SQL filter {!r}: {}".format(rule.row_number, rule.sql_filter, error), source_path)
            else:
                self._add("SQL filter", ValidationStatus.PASS, "FC_Mapping.csv row {} SQL filter is valid.".format(rule.row_number), source_path)

    def _write_report(self) -> str:
        """Write current validation results to the required CSV report.

        Args:
            None.

        Returns:
            Absolute Validation_Report.csv path.

        Raises:
            ReportError: If the report folder or CSV cannot be written.

        Notes:
            The report is emitted even when validation has ERROR results.
        """
        try:
            report_folder = ensure_folder(self.report_folder)
            report_path = report_folder / VALIDATION_REPORT_FILE
            rows = [
                {"Check": result.check, "Status": result.status.value, "Subject": result.subject, "Message": result.message}
                for result in self._results
            ]
            return str(write_csv_rows(report_path, ("Check", "Status", "Subject", "Message"), rows))
        except Exception as error:
            raise ReportError("Unable to write Validation_Report.csv: {}".format(error)) from error

    def _add(self, check: str, status: ValidationStatus, message: str, subject: str = "") -> None:
        """Append one result and mirror it to an optional Logger.

        Args:
            check: Validation category.
            status: Result outcome.
            message: Human-readable diagnostic.
            subject: Optional path or rule identifier.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Logger failures are ignored because validation-report output remains
            the authoritative record.
        """
        result = ValidationResult(check, status, message, subject)
        self._results.append(result)
        if self.logger is None:
            return
        try:
            log_method = {ValidationStatus.PASS: "info", ValidationStatus.WARNING: "warning", ValidationStatus.ERROR: "error"}[status]
            getattr(self.logger, log_method)("{}: {}".format(check, message))
        except Exception:
            pass


def validate(configuration_folder: str, source_gdb: str, template_gdb: str, report_folder: Optional[str] = None, logger: Optional[object] = None) -> ValidationSummary:
    """Convenience function that constructs and runs a Validator.

    Args:
        configuration_folder: Folder containing required configuration CSVs.
        source_gdb: Source geodatabase path.
        template_gdb: Template geodatabase path.
        report_folder: Optional output folder for Validation_Report.csv.
        logger: Optional framework Logger.

    Returns:
        ValidationSummary from the completed validation run.

    Raises:
        ReportError: If Validation_Report.csv cannot be written.

    Notes:
        This is the recommended simple entry point for toolbox integration.
    """
    return Validator(configuration_folder, source_gdb, template_gdb, report_folder, logger).validate()


def _enabled(items: Iterable[object]) -> Iterable[object]:
    """Yield only rule objects whose enabled attribute is true.

    Args:
        items: Rule objects with an enabled boolean attribute.

    Yields:
        Enabled rule objects.

    Raises:
        None.

    Notes:
        Lookup rules are intentionally not passed to this helper.
    """
    return (item for item in items if bool(getattr(item, "enabled", False)))


def _resolve_path(paths: Mapping[str, str], workspace: str, feature_class: str) -> str:
    """Resolve a mapped FC path or use a root-feature-class fallback path.

    Args:
        paths: Case-normalized feature-class path mapping.
        workspace: Source or template geodatabase path.
        feature_class: Requested feature-class name.

    Returns:
        Resolved catalog path.

    Raises:
        None.

    Notes:
        The fallback permits domain/field mappings for an FC not explicitly
        listed in FC_Mapping.csv, which validation then reports accurately.
    """
    return paths.get(feature_class.casefold(), os.path.join(workspace, feature_class))


def _expected_geometry(rule: GeometryRuleName, source_geometry: str) -> Optional[str]:
    """Return geometry type expected after a configured geometry rule.

    Args:
        rule: Geometry transformation rule.
        source_geometry: Source ArcGIS shape type.

    Returns:
        Expected target shape type, or None when rule preserves a valid type.

    Raises:
        None.

    Notes:
        SINGLEPART and PROJECT preserve the source geometry type.
    """
    if rule in {GeometryRuleName.KEEP, GeometryRuleName.SINGLEPART, GeometryRuleName.PROJECT}:
        return source_geometry
    if rule is GeometryRuleName.CENTROID:
        return "Point"
    if rule is GeometryRuleName.BUFFER:
        return "Polygon"
    if rule is GeometryRuleName.BOUNDARY:
        return "Polyline" if source_geometry == "Polygon" else "Point"
    return None


def _field_metadata(fields: Mapping[str, Mapping[str, object]], field_name: str) -> Optional[Mapping[str, object]]:
    """Find case-insensitive field metadata in a field-information mapping.

    Args:
        fields: Field metadata keyed by original field name.
        field_name: Requested field name.

    Returns:
        Field metadata, or None if no matching field exists.

    Raises:
        None.

    Notes:
        ArcGIS field-name casing differs across some workspace types.
    """
    return next((metadata for name, metadata in fields.items() if name.casefold() == field_name.casefold()), None)


def _duplicate_lookup_keys(lookup_rules: Sequence[LookupRule]) -> List[str]:
    """Return duplicate lookup-name/source-value keys in deterministic order.

    Args:
        lookup_rules: Parsed conventional LookupRule values.

    Returns:
        Formatted duplicate keys.

    Raises:
        None.

    Notes:
        Target values may repeat; only source keys must be unique per lookup.
    """
    seen = set()
    duplicates = set()
    for rule in lookup_rules:
        key = "{}:{}".format(rule.lookup_name, rule.source_value)
        normalized = key.casefold()
        if normalized in seen:
            duplicates.add(key)
        seen.add(normalized)
    return sorted(duplicates)


__all__ = ["ValidationResult", "ValidationStatus", "ValidationSummary", "Validator", "validate"]
