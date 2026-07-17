"""Feature-class migration orchestration for Geodatabase Migration Framework.

The migrator inserts transformed source features into an already copied
template geodatabase.  It never creates feature classes, feature datasets,
fields, or domains, and it never uses UpdateCursor.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:  # Supports package imports and ArcGIS Python-toolbox top-level imports.
    from .logger import Logger
    from .rules import (
        DomainRule, FeatureClassRule, FeatureClassRuleName, FieldRule,
        FieldRuleName, LookupRule, RuleSet, load_configuration,
    )
    from .transform import TransformContext, TransformEngine
    from .utils import arcpy_utils, gdb_utils
    from .utils.exception_utils import MigrationError
    from .utils.progress_utils import ProgressManager
except ImportError:  # pragma: no cover - ArcGIS toolbox loading.
    from logger import Logger  # type: ignore
    from rules import (  # type: ignore
        DomainRule, FeatureClassRule, FeatureClassRuleName, FieldRule,
        FieldRuleName, LookupRule, RuleSet, load_configuration,
    )
    from transform import TransformContext, TransformEngine  # type: ignore
    from utils import arcpy_utils, gdb_utils  # type: ignore
    from utils.exception_utils import MigrationError  # type: ignore
    from utils.progress_utils import ProgressManager  # type: ignore


_SHAPE_TOKEN = "SHAPE@"
_FIELD_TOKEN = re.compile(r"!([^!]+)!")
_COPY_RULES = frozenset((FeatureClassRuleName.COPY, FeatureClassRuleName.SPLIT, FeatureClassRuleName.MERGE))
_SOURCE_FREE_FIELD_RULES = frozenset((FieldRuleName.DEFAULT, FieldRuleName.UUID, FieldRuleName.IGNORE))


@dataclass
class FeatureClassStatistics:
    """Mutable execution counts for one source-to-target FC mapping.

    Args:
        source_feature_class: Source feature-class path.
        target_feature_class: Target feature-class path.
        rule_name: COPY, SPLIT, MERGE, EMPTY, or IGNORE rule label.

    Raises:
        None.

    Notes:
        Counts are updated while streaming rows and finalized after a mapping.
    """

    source_feature_class: str
    target_feature_class: str
    rule_name: str
    features_read: int = 0
    features_migrated: int = 0
    features_skipped: int = 0
    features_failed: int = 0
    elapsed_seconds: float = 0.0
    messages: List[str] = field(default_factory=list)
    errors: List["MigrationErrorRecord"] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Return whether this mapping completed without feature failures.

        Args:
            None.

        Returns:
            ``True`` when no feature-level failures were recorded.

        Raises:
            None.

        Notes:
            Skipped features do not make an otherwise valid mapping fail.
        """
        return self.features_failed == 0


@dataclass(frozen=True)
class MigrationErrorRecord:
    """A bounded audit record for one mapping or source-feature failure.

    Args:
        source_feature_class: Source FC catalog path.
        target_feature_class: Target FC catalog path.
        source_row_number: One-based source cursor row number, or None.
        message: Failure explanation safe for logging and reporting.

    Raises:
        None.

    Notes:
        The record deliberately excludes full source-row values, which can be
        sensitive or excessively large in enterprise geodatabases.
    """

    source_feature_class: str
    target_feature_class: str
    source_row_number: Optional[int]
    message: str


@dataclass(frozen=True)
class MigrationOptions:
    """Optional operational controls for a migration run.

    Args:
        continue_on_feature_error: Whether one row failure permits later rows.
        maximum_error_records: Maximum audit records retained per FC mapping.
        validate_field_schema: Whether plans independently check mapped fields.

    Raises:
        ValueError: If maximum_error_records is negative.

    Notes:
        The default continues after row failures while retaining a bounded audit
        trail; this is suitable for long-running enterprise migrations.
    """

    continue_on_feature_error: bool = True
    maximum_error_records: int = 1000
    validate_field_schema: bool = True

    def __post_init__(self) -> None:
        """Validate option values.

        Args:
            None.

        Returns:
            None.

        Raises:
            ValueError: If maximum_error_records is negative.

        Notes:
            Zero disables retained audit records but not normal Logger errors.
        """
        if self.maximum_error_records < 0:
            raise ValueError("maximum_error_records cannot be negative.")


@dataclass(frozen=True)
class MigrationSummary:
    """Immutable aggregate statistics from an entire migration run.

    Args:
        feature_class_statistics: Per-mapping execution metrics.
        elapsed_seconds: Total migration duration.

    Raises:
        None.

    Notes:
        Reports are intentionally not generated here; report.py consumes this
        typed data later.
    """

    feature_class_statistics: Tuple[FeatureClassStatistics, ...]
    elapsed_seconds: float

    @property
    def features_read(self) -> int:
        """Return total source features read.

        Args:
            None.

        Returns:
            Sum of per-mapping source feature counts.

        Raises:
            None.

        Notes:
            A source may be counted multiple times intentionally for SPLIT.
        """
        return sum(item.features_read for item in self.feature_class_statistics)

    @property
    def features_migrated(self) -> int:
        """Return total inserted target features.

        Args:
            None.

        Returns:
            Sum of successful InsertCursor rows.

        Raises:
            None.

        Notes:
            This is the primary completed-feature metric.
        """
        return sum(item.features_migrated for item in self.feature_class_statistics)

    @property
    def features_skipped(self) -> int:
        """Return total features skipped by configuration or processing.

        Args:
            None.

        Returns:
            Sum of skipped feature counts.

        Raises:
            None.

        Notes:
            EMPTY and IGNORE class mappings record their skipped sources here.
        """
        return sum(item.features_skipped for item in self.feature_class_statistics)

    @property
    def features_failed(self) -> int:
        """Return total feature-level transformation or insertion failures.

        Args:
            None.

        Returns:
            Sum of failed feature counts.

        Raises:
            None.

        Notes:
            The migrator continues after individual row failures.
        """
        return sum(item.features_failed for item in self.feature_class_statistics)

    @property
    def success(self) -> bool:
        """Return whether no mapping or feature failure occurred.

        Args:
            None.

        Returns:
            ``True`` when all statistics report success.

        Raises:
            None.

        Notes:
            Skipped rows do not alone make the migration unsuccessful.
        """
        return self.features_failed == 0 and all(item.success for item in self.feature_class_statistics)

    @property
    def mapping_count(self) -> int:
        """Return the number of executed feature-class mapping rules.

        Args:
            None.

        Returns:
            Per-mapping statistic count.

        Raises:
            None.

        Notes:
            SPLIT and MERGE mappings are counted separately for audit clarity.
        """
        return len(self.feature_class_statistics)

    @property
    def error_records(self) -> Tuple[MigrationErrorRecord, ...]:
        """Return all retained source-row and mapping error records.

        Args:
            None.

        Returns:
            Ordered immutable error-record sequence.

        Raises:
            None.

        Notes:
            The list is bounded independently for each feature-class mapping.
        """
        return tuple(record for item in self.feature_class_statistics for record in item.errors)


@dataclass(frozen=True)
class _MigrationPlan:
    """Prepared cursor fields and typed mapping rules for one FC operation."""

    feature_rule: FeatureClassRule
    source_path: str
    target_path: str
    field_rules: Tuple[FieldRule, ...]
    source_fields: Tuple[str, ...]
    target_fields: Tuple[str, ...]


class Migrator:
    """Stream typed GMF mapping rules from source GDB into copied template GDB.

    Args:
        source_gdb: Existing source geodatabase catalog path.
        target_gdb: Existing output geodatabase copied from the template.
        rule_set: Typed configuration rules loaded by rules.py.
        logger: Optional Logger; a new Logger is used when omitted.
        domain_mappings: Optional named source-to-target domain maps.
        lookup_tables: Optional named source-to-target lookup maps.
        concat_separator: Separator passed to CONCAT transformations.

    Raises:
        ValueError: If required paths or rule_set are absent.

    Notes:
        The target schema must already exist.  Use ``prepare_output`` before
        construction when this class is the owner of template copying.
    """

    def __init__(
        self,
        source_gdb: str,
        target_gdb: str,
        rule_set: RuleSet,
        logger: Optional[Logger] = None,
        domain_mappings: Optional[Mapping[str, Mapping[Any, Any]]] = None,
        lookup_tables: Optional[Mapping[str, Mapping[Any, Any]]] = None,
        concat_separator: str = "",
        options: Optional[MigrationOptions] = None,
    ) -> None:
        """Create a migration service without opening cursors.

        Args:
            source_gdb: Source GDB path.
            target_gdb: Copied template GDB path.
            rule_set: Typed GMF rules.
            logger: Optional existing Logger.
            domain_mappings: Optional prebuilt domain mappings.
            lookup_tables: Optional prebuilt lookup mappings.
            concat_separator: CONCAT join separator.
            options: Optional migration execution controls.

        Returns:
            None.

        Raises:
            ValueError: If source_gdb, target_gdb, or rule_set is invalid.

        Notes:
            Mapping tables are copied into local dictionaries to avoid mutation
            of caller-owned configuration values during migration.
        """
        if not source_gdb or not target_gdb or not isinstance(rule_set, RuleSet):
            raise ValueError("source_gdb, target_gdb, and a typed RuleSet are required.")
        self.source_gdb = source_gdb
        self.target_gdb = target_gdb
        self.rule_set = rule_set
        self.logger = logger or Logger()
        self._owns_logger = logger is None
        self.domain_mappings = dict(domain_mappings or _build_domain_mappings(rule_set.domain_rules, rule_set.field_rules))
        self.lookup_tables = dict(lookup_tables or _build_lookup_tables(rule_set.lookup_rules))
        self.concat_separator = concat_separator
        self.options = options or MigrationOptions()
        self._transform_engine = TransformEngine()
        # Reuse Describe results when several mapping rows reference the same
        # source or target feature class.  The cache is local to this run so
        # it cannot become stale between independent toolbox executions.
        self._metadata_cache = gdb_utils.MetadataCache()

    @staticmethod
    def prepare_output(template_gdb: str, output_gdb: str, overwrite: bool = False) -> str:
        """Copy the template geodatabase to create a migration target.

        Args:
            template_gdb: Existing template geodatabase.
            output_gdb: Requested output geodatabase path.
            overwrite: Whether an existing output may be replaced.

        Returns:
            Created output geodatabase path.

        Raises:
            MigrationError: If safe template copying fails.

        Notes:
            This performs only a geodatabase copy and never alters schema.
        """
        return gdb_utils.copy_template_geodatabase(template_gdb, output_gdb, overwrite)

    def migrate(self) -> MigrationSummary:
        """Execute all enabled COPY, SPLIT, and MERGE mapping rules.

        Args:
            None.

        Returns:
            Immutable MigrationSummary with per-mapping statistics.

        Raises:
            MigrationError: If source or target workspace preconditions fail.

        Notes:
            Feature-level transformation and insert failures are logged and
            counted without abandoning remaining source rows or mappings.
        """
        started_at = perf_counter()
        statistics: List[FeatureClassStatistics] = []
        active_rules = tuple(rule for rule in self.rule_set.feature_class_rules if rule.enabled)
        self._validate_workspaces()
        self.logger.section("Migration")
        self.logger.info("Source geodatabase: {}".format(self.source_gdb))
        self.logger.info("Target geodatabase: {}".format(self.target_gdb))
        self.logger.info("Enabled feature-class rules: {}".format(len(active_rules)))

        progress = ProgressManager(len(active_rules), "Migrating feature classes")
        progress_started = False
        try:
            progress.start()
            progress_started = True
            for rule in active_rules:
                item = self._migrate_rule(rule)
                statistics.append(item)
                label = "{}: {} read, {} migrated, {} failed".format(
                    os.path.basename(item.target_feature_class) or item.target_feature_class,
                    item.features_read, item.features_migrated, item.features_failed,
                )
                progress.update(label)
        finally:
            if progress_started:
                progress.finish()

        summary = MigrationSummary(tuple(statistics), round(perf_counter() - started_at, 3))
        self._log_summary(summary)
        if self._owns_logger:
            self.logger.close()
        return summary

    def _validate_workspaces(self) -> None:
        """Validate source and target GDBs before cursors are opened.

        Args:
            None.

        Returns:
            None.

        Raises:
            MigrationError: If either workspace is unavailable or invalid.

        Notes:
            Target is expected to be the copied template, not the template
            itself, so migrations cannot accidentally populate the template.
        """
        try:
            gdb_utils.validate_geodatabase(self.source_gdb, "Source geodatabase")
            gdb_utils.validate_geodatabase(self.target_gdb, "Target geodatabase")
        except Exception as error:
            raise MigrationError("Migration workspace validation failed: {}".format(error)) from error

    def _migrate_rule(self, rule: FeatureClassRule) -> FeatureClassStatistics:
        """Execute one feature-class rule and always return its statistics.

        Args:
            rule: Enabled typed feature-class mapping rule.

        Returns:
            FeatureClassStatistics for the mapping.

        Raises:
            None.

        Notes:
            Rule-level errors are recorded as a failed statistic so later
            feature classes remain eligible for migration.
        """
        source_path = gdb_utils.feature_class_path(self.source_gdb, rule.source_dataset, rule.source_feature_class)
        target_path = gdb_utils.feature_class_path(self.target_gdb, rule.target_dataset, rule.target_feature_class) if rule.target_feature_class else ""
        statistic = FeatureClassStatistics(source_path, target_path, rule.rule.value)
        mapping_started_at = perf_counter()
        self.logger.section("{} {} -> {}".format(rule.rule.value, source_path, target_path or "(none)"))
        try:
            if rule.rule in {FeatureClassRuleName.IGNORE, FeatureClassRuleName.EMPTY}:
                statistic.features_skipped = self._count_source_features(source_path, rule.sql_filter)
                self.logger.info("{} rule skipped {} source features.".format(rule.rule.value, statistic.features_skipped))
            elif rule.rule in _COPY_RULES:
                plan = self._build_plan(rule, source_path, target_path)
                self._execute_plan(plan, statistic)
            else:
                raise MigrationError("Unsupported feature-class rule: {}".format(rule.rule.value))
        except Exception as error:
            statistic.features_failed += 1
            message = "Feature-class rule failed: {}".format(error)
            statistic.messages.append(message)
            self._record_error(statistic, None, message)
            self.logger.error(message)
        statistic.elapsed_seconds = round(perf_counter() - mapping_started_at, 3)
        self.logger.statistics(
            "Feature class statistics",
            {
                "Rule": statistic.rule_name,
                "Features read": statistic.features_read,
                "Features migrated": statistic.features_migrated,
                "Features skipped": statistic.features_skipped,
                "Features failed": statistic.features_failed,
                "Elapsed seconds": statistic.elapsed_seconds,
            },
        )
        return statistic

    def _count_source_features(self, source_path: str, where_clause: Optional[str]) -> int:
        """Count source rows using SearchCursor without changing data.

        Args:
            source_path: Source feature class.
            where_clause: Optional configured SQL filter.

        Returns:
            Number of selected source features.

        Raises:
            MigrationError: If the read-only cursor cannot be opened.

        Notes:
            This avoids GetCount variations and keeps all row access cursor-only.
        """
        count = 0
        with arcpy_utils.search_cursor(source_path, ["OID@"], where_clause) as cursor:
            for _ in cursor:
                count += 1
        return count

    def _build_plan(self, rule: FeatureClassRule, source_path: str, target_path: str) -> _MigrationPlan:
        """Prepare field rules and explicit cursor fields for one mapping.

        Args:
            rule: COPY, SPLIT, or MERGE feature-class rule.
            source_path: Resolved source FC path.
            target_path: Resolved target FC path.

        Returns:
            Immutable migration plan.

        Raises:
            MigrationError: If source/target feature classes are invalid.

        Notes:
            The source and target schema are inspected only, never changed.
        """
        gdb_utils.validate_feature_class(source_path, self._metadata_cache)
        gdb_utils.validate_feature_class(target_path, self._metadata_cache)
        field_rules = tuple(
            field_rule for field_rule in self.rule_set.field_rules
            if field_rule.enabled
            and field_rule.target_feature_class.casefold() == rule.target_feature_class.casefold()
            and field_rule.source_feature_class.casefold() == rule.source_feature_class.casefold()
        )
        source_fields = _source_cursor_fields(field_rules)
        target_fields = _target_cursor_fields(field_rules)
        if self.options.validate_field_schema:
            self._validate_plan_schema(source_path, target_path, field_rules, source_fields, target_fields)
        return _MigrationPlan(rule, source_path, target_path, field_rules, source_fields, target_fields)

    def _validate_plan_schema(
        self,
        source_path: str,
        target_path: str,
        field_rules: Sequence[FieldRule],
        source_fields: Sequence[str],
        target_fields: Sequence[str],
    ) -> None:
        """Independently verify cursor fields against source and target schema.

        Args:
            source_path: Source feature-class catalog path.
            target_path: Target feature-class catalog path.
            field_rules: Applicable typed field rules.
            source_fields: Planned SearchCursor fields.
            target_fields: Planned InsertCursor fields.

        Returns:
            None.

        Raises:
            MigrationError: If a mapped field is missing or target assignments
                conflict.

        Notes:
            Validation normally checks this earlier; repeating the minimal
            checks here protects direct Migrator usage outside Validator.
        """
        source_names = {name.casefold() for name in gdb_utils.list_field_names(source_path)}
        target_names = {name.casefold() for name in gdb_utils.list_field_names(target_path)}
        missing_source = [name for name in source_fields if name != _SHAPE_TOKEN and name.casefold() not in source_names]
        missing_target = [name for name in target_fields if name != _SHAPE_TOKEN and name.casefold() not in target_names]
        if missing_source:
            raise MigrationError("Source fields missing from {}: {}".format(source_path, ", ".join(missing_source)))
        if missing_target:
            raise MigrationError("Target fields missing from {}: {}".format(target_path, ", ".join(missing_target)))
        assignments: Dict[str, FieldRule] = {}
        for field_rule in field_rules:
            if field_rule.rule is FieldRuleName.IGNORE:
                continue
            key = field_rule.target_field.casefold()
            if key in assignments:
                earlier = assignments[key]
                raise MigrationError(
                    "Conflicting field rules map {} to target {} (rows {} and {})."
                    .format(field_rule.source_feature_class, field_rule.target_field, earlier.row_number, field_rule.row_number)
                )
            assignments[key] = field_rule

    def _execute_plan(self, plan: _MigrationPlan, statistic: FeatureClassStatistics) -> None:
        """Stream source features through field transforms into InsertCursor rows.

        Args:
            plan: Prepared cursor and mapping plan.
            statistic: Mutable statistics to update.

        Returns:
            None.

        Raises:
            MigrationError: If source/target cursor creation fails.

        Notes:
            Only feature-level transform/insert failures are handled locally;
            a cursor opening error fails the mapping and is recorded by caller.
        """
        with arcpy_utils.search_cursor(plan.source_path, plan.source_fields, plan.feature_rule.sql_filter) as source_cursor:
            with arcpy_utils.insert_cursor(plan.target_path, plan.target_fields) as target_cursor:
                for row_number, source_values in enumerate(source_cursor, start=1):
                    statistic.features_read += 1
                    try:
                        source_row = dict(zip(plan.source_fields, source_values))
                        target_values = self._transform_feature(plan, source_row)
                        target_cursor.insertRow(tuple(target_values[field_name] for field_name in plan.target_fields))
                    except Exception as error:
                        statistic.features_failed += 1
                        message = "{} row {} failed: {}".format(plan.source_path, row_number, error)
                        statistic.messages.append(message)
                        self._record_error(statistic, row_number, message)
                        self.logger.error(message)
                        if not self.options.continue_on_feature_error:
                            raise MigrationError(message) from error
                    else:
                        statistic.features_migrated += 1

    def _transform_feature(self, plan: _MigrationPlan, source_row: Mapping[str, Any]) -> Dict[str, Any]:
        """Transform one source cursor row into target InsertCursor values.

        Args:
            plan: Prepared field-rule plan.
            source_row: Source values keyed by cursor-field name.

        Returns:
            Target values keyed by InsertCursor field name.

        Raises:
            MigrationError: If a field transform or geometry transfer is invalid.

        Notes:
            Geometry is copied as SHAPE@.  Other geometry transformations are
            deliberately rejected until a dedicated geometry transformer exists.
        """
        if plan.feature_rule.geometry_rule.value != "KEEP":
            raise MigrationError("Geometry rule {} is not implemented by migrator yet.".format(plan.feature_rule.geometry_rule.value))
        values: Dict[str, Any] = {_SHAPE_TOKEN: source_row[_SHAPE_TOKEN]}
        context = TransformContext(source_row, self.domain_mappings, self.lookup_tables, self.concat_separator)
        for field_rule in plan.field_rules:
            result = self._transform_engine.transform(field_rule, context)
            if result.assign:
                values[field_rule.target_field] = result.value
        for target_field in plan.target_fields:
            if target_field not in values:
                # An IGNORE rule cannot be placed in an InsertCursor field list;
                # this guard makes an incomplete plan a clear migration error.
                raise MigrationError("No transformed value is available for target field {}.".format(target_field))
        return values

    def _record_error(self, statistic: FeatureClassStatistics, row_number: Optional[int], message: str) -> None:
        """Store a bounded migration audit record for an encountered failure.

        Args:
            statistic: Mapping statistics to update.
            row_number: Optional one-based source row number.
            message: Failure message.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Logger still receives every error even after the audit-record cap.
        """
        if len(statistic.errors) >= self.options.maximum_error_records:
            return
        statistic.errors.append(
            MigrationErrorRecord(
                statistic.source_feature_class,
                statistic.target_feature_class,
                row_number,
                message,
            )
        )

    def _log_summary(self, summary: MigrationSummary) -> None:
        """Write final aggregate migration statistics through Logger.

        Args:
            summary: Completed migration result.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Reporting remains separate; Logger statistics are diagnostics only.
        """
        self.logger.section("Migration complete")
        self.logger.statistics(
            "Migration summary",
            {
                "Feature class mappings": len(summary.feature_class_statistics),
                "Features read": summary.features_read,
                "Features migrated": summary.features_migrated,
                "Features skipped": summary.features_skipped,
                "Features failed": summary.features_failed,
                "Elapsed seconds": summary.elapsed_seconds,
                "Success": summary.success,
                "Retained error records": len(summary.error_records),
            },
        )


def migrate_from_configuration(
    configuration_folder: str,
    source_gdb: str,
    template_gdb: str,
    output_gdb: str,
    overwrite: bool = False,
    logger: Optional[Logger] = None,
) -> MigrationSummary:
    """Copy template, load typed configuration, and execute a migration.

    Args:
        configuration_folder: Folder containing GMF mapping CSV files.
        source_gdb: Existing source geodatabase.
        template_gdb: Existing schema template geodatabase.
        output_gdb: New target geodatabase path.
        overwrite: Whether an existing output may be replaced.
        logger: Optional Logger instance.

    Returns:
        Completed MigrationSummary.

    Raises:
        MigrationError: If template copying, rule loading, or migration fails.

    Notes:
        This is the high-level workflow entry point; Migrator itself accepts a
        pre-copied target for callers that already manage output preparation.
    """
    try:
        target_gdb = Migrator.prepare_output(template_gdb, output_gdb, overwrite)
        rule_set = load_configuration(configuration_folder)
        return Migrator(source_gdb, target_gdb, rule_set, logger).migrate()
    except MigrationError:
        raise
    except Exception as error:
        raise MigrationError("Migration initialization failed: {}".format(error)) from error


def _source_cursor_fields(field_rules: Sequence[FieldRule]) -> Tuple[str, ...]:
    """Return unique source fields required for transforms plus SHAPE@.

    Args:
        field_rules: Enabled field rules for one mapping.

    Returns:
        Ordered source cursor fields.

    Raises:
        None.

    Notes:
        Expression field tokens and CONCAT parameters are included to prevent
        repeated cursor access or loading an entire source schema.
    """
    fields: List[str] = [_SHAPE_TOKEN]
    for rule in field_rules:
        if rule.rule not in _SOURCE_FREE_FIELD_RULES and rule.source_field:
            _append_unique(fields, rule.source_field)
        if rule.rule is FieldRuleName.CONCAT:
            for field_name in (rule.parameter or "").split(","):
                if field_name.strip():
                    _append_unique(fields, field_name.strip())
        if rule.rule in {FieldRuleName.EXPRESSION, FieldRuleName.CALCULATE}:
            for field_name in _FIELD_TOKEN.findall(rule.parameter or ""):
                _append_unique(fields, field_name.strip())
    return tuple(fields)


def _target_cursor_fields(field_rules: Sequence[FieldRule]) -> Tuple[str, ...]:
    """Return unique target InsertCursor fields plus SHAPE@.

    Args:
        field_rules: Enabled field rules for one mapping.

    Returns:
        Ordered target cursor fields.

    Raises:
        None.

    Notes:
        IGNORE target fields are omitted so they are not assigned during insert.
    """
    fields: List[str] = [_SHAPE_TOKEN]
    for rule in field_rules:
        if rule.rule is not FieldRuleName.IGNORE:
            _append_unique(fields, rule.target_field)
    return tuple(fields)


def _append_unique(values: List[str], value: str) -> None:
    """Append a field name only when it is not already present case-insensitively.

    Args:
        values: Mutable ordered field collection.
        value: Field name to append.

    Returns:
        None.

    Raises:
        None.

    Notes:
        ArcGIS field names can vary in casing between source and target systems.
    """
    if not any(current.casefold() == value.casefold() for current in values):
        values.append(value)


def _build_domain_mappings(domain_rules: Sequence[DomainRule], field_rules: Sequence[FieldRule]) -> Dict[str, Dict[Any, Any]]:
    """Build named domain maps consumed by DomainTransformer.

    Args:
        domain_rules: Typed source-code to target-code mappings.
        field_rules: Field rules used to associate DOMAIN parameters to fields.

    Returns:
        Mapping name to source-code/target-code dictionary.

    Raises:
        None.

    Notes:
        A DOMAIN parameter is preferred; a target FC/field key is also added
        for explicit programmatic use when a parameter is unavailable.
    """
    result: Dict[str, Dict[Any, Any]] = {}
    domains_by_target: Dict[Tuple[str, str], Dict[Any, Any]] = {}
    for rule in domain_rules:
        if not rule.enabled:
            continue
        key = (rule.target_feature_class.casefold(), rule.target_field.casefold())
        domains_by_target.setdefault(key, {})[rule.source_code] = rule.target_code
    for field_rule in field_rules:
        if field_rule.enabled and field_rule.rule is FieldRuleName.DOMAIN:
            key = (field_rule.target_feature_class.casefold(), field_rule.target_field.casefold())
            mapping = domains_by_target.get(key, {})
            if field_rule.parameter:
                result[field_rule.parameter] = mapping
            result["{}.{}".format(field_rule.target_feature_class, field_rule.target_field)] = mapping
    return result


def _build_lookup_tables(lookup_rules: Sequence[object]) -> Dict[str, Dict[Any, Any]]:
    """Build named lookup tables from typed conventional LookupRule values.

    Args:
        lookup_rules: Parsed lookup values or lookup-column definitions.

    Returns:
        Named source-value/target-value tables.

    Raises:
        None.

    Notes:
        LookupColumnRule definitions intentionally do not generate values; a
        LOOKUP field rule then reports a clear missing mapping during migration.
    """
    tables: Dict[str, Dict[Any, Any]] = {}
    for rule in lookup_rules:
        if isinstance(rule, LookupRule):
            tables.setdefault(rule.lookup_name, {})[rule.source_value] = rule.target_value
    return tables


__all__ = [
    "FeatureClassStatistics", "MigrationErrorRecord", "MigrationOptions",
    "MigrationSummary", "Migrator", "migrate_from_configuration",
]
