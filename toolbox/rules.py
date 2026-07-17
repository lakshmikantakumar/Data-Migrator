"""Typed, validated configuration rules for Geodatabase Migration Framework.

This module reads the four GMF configuration CSV files and converts each row
into an immutable typed rule.  It deliberately contains no migration,
geoprocessing, report-generation, or schema-modification logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

try:  # Supports both package imports and ArcGIS toolbox top-level imports.
    from .utils.constants import (
        DOMAIN_MAPPING_FILE, FC_MAPPING_FILE, FEATURE_CLASS_RULES,
        FIELD_MAPPING_FILE, FIELD_RULES, GEOMETRY_KEEP, GEOMETRY_RULES,
        LOOKUP_FILE,
    )
    from .utils.exception_utils import ConfigurationError
    from .utils.file_utils import configuration_file, read_csv_rows
except ImportError:  # pragma: no cover - exercised by ArcGIS toolbox loading.
    from utils.constants import (  # type: ignore
        DOMAIN_MAPPING_FILE, FC_MAPPING_FILE, FEATURE_CLASS_RULES,
        FIELD_MAPPING_FILE, FIELD_RULES, GEOMETRY_KEEP, GEOMETRY_RULES,
        LOOKUP_FILE,
    )
    from utils.exception_utils import ConfigurationError  # type: ignore
    from utils.file_utils import configuration_file, read_csv_rows  # type: ignore


_TRUE_VALUES = frozenset(("yes", "true", "1", "y"))
_FALSE_VALUES = frozenset(("no", "false", "0", "n", ""))

_FC_COLUMNS = (
    "Enabled", "Source_Dataset", "Source_FeatureClass", "Target_Dataset",
    "Target_FeatureClass", "Rule", "Filter", "Geometry_Rule",
)
_FIELD_COLUMNS = (
    "Enabled", "Source_FeatureClass", "Source_Field", "Target_FeatureClass",
    "Target_Field", "Rule", "Parameter", "Default_Value",
)
_DOMAIN_COLUMNS = (
    "Enabled", "Source_FeatureClass", "Source_Field", "Source_Code",
    "Target_FeatureClass", "Target_Field", "Target_Code", "Description",
)
_LOOKUP_VALUE_COLUMNS = ("Lookup_Name", "Source_Value", "Target_Value", "Description")
_LOOKUP_DEFINITION_COLUMNS = ("Column", "Required", "Description")


class FeatureClassRuleName(str, Enum):
    """Supported feature-class migration rule names."""

    COPY = "COPY"
    SPLIT = "SPLIT"
    MERGE = "MERGE"
    IGNORE = "IGNORE"
    EMPTY = "EMPTY"


class FieldRuleName(str, Enum):
    """Supported field transformation rule names."""

    COPY = "COPY"
    DOMAIN = "DOMAIN"
    DEFAULT = "DEFAULT"
    UUID = "UUID"
    LOOKUP = "LOOKUP"
    EXPRESSION = "EXPRESSION"
    CONCAT = "CONCAT"
    SPLIT = "SPLIT"
    SUBSTRING = "SUBSTRING"
    DATEFORMAT = "DATEFORMAT"
    CALCULATE = "CALCULATE"
    IGNORE = "IGNORE"


class GeometryRuleName(str, Enum):
    """Supported geometry transformation rule names."""

    KEEP = "KEEP"
    SINGLEPART = "SINGLEPART"
    CENTROID = "CENTROID"
    BOUNDARY = "BOUNDARY"
    BUFFER = "BUFFER"
    PROJECT = "PROJECT"


@dataclass(frozen=True)
class FeatureClassRule:
    """Mapping and transform settings for one source-to-target feature class."""

    enabled: bool
    source_dataset: Optional[str]
    source_feature_class: str
    target_dataset: Optional[str]
    target_feature_class: str
    rule: FeatureClassRuleName
    sql_filter: Optional[str]
    geometry_rule: GeometryRuleName
    row_number: int


@dataclass(frozen=True)
class FieldRule:
    """Transformation settings for one target feature-class field."""

    enabled: bool
    source_feature_class: str
    source_field: Optional[str]
    target_feature_class: str
    target_field: str
    rule: FieldRuleName
    parameter: Optional[str]
    default_value: Optional[str]
    row_number: int


@dataclass(frozen=True)
class DomainRule:
    """Code-to-code domain value mapping for a target field."""

    enabled: bool
    source_feature_class: str
    source_field: str
    source_code: str
    target_feature_class: str
    target_field: str
    target_code: str
    description: Optional[str]
    row_number: int


@dataclass(frozen=True)
class LookupRule:
    """A value translation entry from a conventional lookup CSV."""

    lookup_name: str
    source_value: str
    target_value: str
    description: Optional[str]
    row_number: int


@dataclass(frozen=True)
class LookupColumnRule:
    """A lookup-table column definition from the supplied Lookup.csv format."""

    column_name: str
    required: bool
    description: Optional[str]
    row_number: int


LookupConfigurationRule = Union[LookupRule, LookupColumnRule]


@dataclass(frozen=True)
class RuleSet:
    """Complete immutable rule collection read from one configuration folder."""

    feature_class_rules: Tuple[FeatureClassRule, ...]
    field_rules: Tuple[FieldRule, ...]
    domain_rules: Tuple[DomainRule, ...]
    lookup_rules: Tuple[LookupConfigurationRule, ...]


def load_feature_class_rules(configuration_folder: str) -> Tuple[FeatureClassRule, ...]:
    """Read FC_Mapping.csv and return validated feature-class rules.

    Args:
        configuration_folder: Folder containing the required mapping CSVs.

    Returns:
        Immutable sequence of FeatureClassRule objects.

    Raises:
        ConfigurationError: If required columns or rule values are invalid.

    Notes:
        Disabled rows are retained so validation and audit code can inspect
        the complete user-supplied configuration.
    """
    rows = _read_mapping_file(configuration_folder, FC_MAPPING_FILE, _FC_COLUMNS)
    return tuple(_feature_class_rule(row, number) for number, row in enumerate(rows, start=2))


def load_field_rules(configuration_folder: str) -> Tuple[FieldRule, ...]:
    """Read Field_Mapping.csv and return validated field rules.

    Args:
        configuration_folder: Folder containing the required mapping CSVs.

    Returns:
        Immutable sequence of FieldRule objects.

    Raises:
        ConfigurationError: If required columns or rule values are invalid.

    Notes:
        Rule-specific source-field checks prevent invalid DEFAULT and UUID
        mappings while still permitting their intentionally blank source.
    """
    rows = _read_mapping_file(configuration_folder, FIELD_MAPPING_FILE, _FIELD_COLUMNS)
    return tuple(_field_rule(row, number) for number, row in enumerate(rows, start=2))


def load_domain_rules(configuration_folder: str) -> Tuple[DomainRule, ...]:
    """Read Domain_Mapping.csv and return validated domain value rules.

    Args:
        configuration_folder: Folder containing the required mapping CSVs.

    Returns:
        Immutable sequence of DomainRule objects.

    Raises:
        ConfigurationError: If required columns or required values are absent.

    Notes:
        Domain rules are mapping metadata only; they never create or modify a
        geodatabase domain.
    """
    rows = _read_mapping_file(configuration_folder, DOMAIN_MAPPING_FILE, _DOMAIN_COLUMNS)
    return tuple(_domain_rule(row, number) for number, row in enumerate(rows, start=2))


def load_lookup_rules(configuration_folder: str) -> Tuple[LookupConfigurationRule, ...]:
    """Read Lookup.csv in either value-map or column-definition format.

    Args:
        configuration_folder: Folder containing the required mapping CSVs.

    Returns:
        Immutable sequence of LookupRule or LookupColumnRule objects.

    Raises:
        ConfigurationError: If the CSV uses neither supported mandatory header
            set or contains invalid required values.

    Notes:
        The supplied AMRUT file uses the column-definition format.  Supporting
        both forms allows a project to provide actual lookup values later.
    """
    path = configuration_file(configuration_folder, LOOKUP_FILE)
    try:
        value_rows = read_csv_rows(path, _LOOKUP_VALUE_COLUMNS)
    except ConfigurationError as value_error:
        try:
            definition_rows = read_csv_rows(path, _LOOKUP_DEFINITION_COLUMNS)
        except ConfigurationError:
            raise ConfigurationError(
                "Lookup.csv must contain either {} or {} columns."
                .format(", ".join(_LOOKUP_VALUE_COLUMNS), ", ".join(_LOOKUP_DEFINITION_COLUMNS))
            ) from value_error
        return tuple(_lookup_column_rule(row, number) for number, row in enumerate(definition_rows, start=2))
    return tuple(_lookup_rule(row, number) for number, row in enumerate(value_rows, start=2))


def load_configuration(configuration_folder: str) -> RuleSet:
    """Read every required GMF configuration file into one typed RuleSet.

    Args:
        configuration_folder: Folder containing all four required CSV files.

    Returns:
        Immutable RuleSet containing every parsed mapping rule.

    Raises:
        ConfigurationError: If any required file, column, or rule value is
            invalid.

    Notes:
        Files are loaded independently so errors identify the actual faulty
        configuration source rather than being obscured by later processing.
    """
    return RuleSet(
        feature_class_rules=load_feature_class_rules(configuration_folder),
        field_rules=load_field_rules(configuration_folder),
        domain_rules=load_domain_rules(configuration_folder),
        lookup_rules=load_lookup_rules(configuration_folder),
    )


def _read_mapping_file(folder: str, filename: str, required_columns: Sequence[str]) -> List[dict[str, str]]:
    """Read one required CSV and attach its filename to validation failures.

    Args:
        folder: Configuration folder.
        filename: Required CSV filename.
        required_columns: Mandatory CSV headers.

    Returns:
        Normalized CSV row dictionaries.

    Raises:
        ConfigurationError: If the file cannot satisfy the required schema.

    Notes:
        Row values are converted into dataclasses by the specific loaders.
    """
    path = configuration_file(folder, filename)
    try:
        return read_csv_rows(path, required_columns)
    except ConfigurationError as error:
        raise ConfigurationError("Invalid {}: {}".format(filename, error)) from error


def _feature_class_rule(row: Mapping[str, str], row_number: int) -> FeatureClassRule:
    """Convert one validated FC mapping row into a FeatureClassRule.

    Args:
        row: Normalized FC_Mapping.csv values.
        row_number: Original CSV row number.

    Returns:
        Typed FeatureClassRule.

    Raises:
        ConfigurationError: If a mandatory value or rule label is invalid.

    Notes:
        Empty geometry rules intentionally normalize to KEEP.
    """
    context = "FC_Mapping.csv row {}".format(row_number)
    rule = _feature_class_rule_name(_required(row, "Rule", context), context)
    source = _required(row, "Source_FeatureClass", context)
    target = _optional(row, "Target_FeatureClass")
    if rule is not FeatureClassRuleName.IGNORE and not target:
        raise ConfigurationError("{} requires Target_FeatureClass.".format(context))
    return FeatureClassRule(
        enabled=_enabled(row, context), source_dataset=_optional(row, "Source_Dataset"),
        source_feature_class=source, target_dataset=_optional(row, "Target_Dataset"),
        target_feature_class=target or "", rule=rule, sql_filter=_optional(row, "Filter"),
        geometry_rule=_geometry_rule_name(_optional(row, "Geometry_Rule") or GEOMETRY_KEEP, context),
        row_number=row_number,
    )


def _field_rule(row: Mapping[str, str], row_number: int) -> FieldRule:
    """Convert one Field mapping row into a FieldRule.

    Args:
        row: Normalized Field_Mapping.csv values.
        row_number: Original CSV row number.

    Returns:
        Typed FieldRule.

    Raises:
        ConfigurationError: If required mapping values are invalid.

    Notes:
        DEFAULT and UUID intentionally do not require Source_Field.
    """
    context = "Field_Mapping.csv row {}".format(row_number)
    rule = _field_rule_name(_required(row, "Rule", context), context)
    source_field = _optional(row, "Source_Field")
    if rule not in {FieldRuleName.DEFAULT, FieldRuleName.UUID, FieldRuleName.IGNORE} and not source_field:
        raise ConfigurationError("{} requires Source_Field for {}.".format(context, rule.value))
    if rule is FieldRuleName.DEFAULT and _optional(row, "Default_Value") is None:
        raise ConfigurationError("{} requires Default_Value for DEFAULT.".format(context))
    return FieldRule(
        enabled=_enabled(row, context), source_feature_class=_required(row, "Source_FeatureClass", context),
        source_field=source_field, target_feature_class=_required(row, "Target_FeatureClass", context),
        target_field=_required(row, "Target_Field", context), rule=rule,
        parameter=_optional(row, "Parameter"), default_value=_optional(row, "Default_Value"),
        row_number=row_number,
    )


def _domain_rule(row: Mapping[str, str], row_number: int) -> DomainRule:
    """Convert one domain mapping row into a DomainRule.

    Args:
        row: Normalized Domain_Mapping.csv values.
        row_number: Original CSV row number.

    Returns:
        Typed DomainRule.

    Raises:
        ConfigurationError: If a mandatory mapping value is missing.

    Notes:
        Code values remain strings to preserve leading zeros.
    """
    context = "Domain_Mapping.csv row {}".format(row_number)
    return DomainRule(
        enabled=_enabled(row, context), source_feature_class=_required(row, "Source_FeatureClass", context),
        source_field=_required(row, "Source_Field", context), source_code=_required(row, "Source_Code", context),
        target_feature_class=_required(row, "Target_FeatureClass", context),
        target_field=_required(row, "Target_Field", context), target_code=_required(row, "Target_Code", context),
        description=_optional(row, "Description"), row_number=row_number,
    )


def _lookup_rule(row: Mapping[str, str], row_number: int) -> LookupRule:
    """Convert a lookup value row into a LookupRule.

    Args:
        row: Normalized conventional Lookup.csv values.
        row_number: Original CSV row number.

    Returns:
        Typed LookupRule.

    Raises:
        ConfigurationError: If a mandatory lookup value is missing.

    Notes:
        Values remain strings because lookup code values can have leading zeros.
    """
    context = "Lookup.csv row {}".format(row_number)
    return LookupRule(
        lookup_name=_required(row, "Lookup_Name", context), source_value=_required(row, "Source_Value", context),
        target_value=_required(row, "Target_Value", context), description=_optional(row, "Description"),
        row_number=row_number,
    )


def _lookup_column_rule(row: Mapping[str, str], row_number: int) -> LookupColumnRule:
    """Convert a supplied lookup-column definition row into a typed rule.

    Args:
        row: Normalized Lookup.csv definition values.
        row_number: Original CSV row number.

    Returns:
        Typed LookupColumnRule.

    Raises:
        ConfigurationError: If the column name or Required value is invalid.

    Notes:
        This supports the schema manifest currently supplied with GMF configs.
    """
    context = "Lookup.csv row {}".format(row_number)
    required_text = _required(row, "Required", context)
    return LookupColumnRule(
        column_name=_required(row, "Column", context), required=_parse_boolean(required_text, context),
        description=_optional(row, "Description"), row_number=row_number,
    )


def _enabled(row: Mapping[str, str], context: str) -> bool:
    """Read an Enabled column as a strict boolean value.

    Args:
        row: Mapping row containing Enabled.
        context: CSV location for error messages.

    Returns:
        Parsed enabled flag.

    Raises:
        ConfigurationError: If Enabled is missing or invalid.

    Notes:
        Yes/No, True/False, and 1/0 are accepted case-insensitively.
    """
    return _parse_boolean(_required(row, "Enabled", context), context)


def _parse_boolean(value: str, context: str) -> bool:
    """Parse a strict CSV boolean value.

    Args:
        value: Text value from a CSV cell.
        context: CSV location for error messages.

    Returns:
        Parsed boolean.

    Raises:
        ConfigurationError: If value is not an accepted boolean spelling.

    Notes:
        Empty values are only accepted where an optional Boolean is defined.
    """
    normalized = value.strip().casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ConfigurationError("{} has invalid Boolean value {!r}.".format(context, value))


def _required(row: Mapping[str, str], column: str, context: str) -> str:
    """Return a non-empty mandatory value from a normalized CSV row.

    Args:
        row: CSV row.
        column: Required column name.
        context: CSV location for error messages.

    Returns:
        Non-empty cell value.

    Raises:
        ConfigurationError: If the required cell is blank.

    Notes:
        Header validation occurs before this value-level validation.
    """
    value = _optional(row, column)
    if value is None:
        raise ConfigurationError("{} requires a value for {}.".format(context, column))
    return value


def _optional(row: Mapping[str, str], column: str) -> Optional[str]:
    """Return a stripped optional CSV value or None when it is blank.

    Args:
        row: CSV row.
        column: Column name to retrieve.

    Returns:
        Stripped value or None.

    Raises:
        None.

    Notes:
        read_csv_rows already normalizes values; this also handles direct use.
    """
    value = row.get(column, "").strip()
    return value or None


def _feature_class_rule_name(value: str, context: str) -> FeatureClassRuleName:
    """Validate and convert a feature-class rule name.

    Args:
        value: Rule text from CSV.
        context: CSV location for errors.

    Returns:
        FeatureClassRuleName enum member.

    Raises:
        ConfigurationError: If the rule is unsupported.

    Notes:
        Constants remain the source of truth for supported values.
    """
    normalized = value.strip().upper()
    if normalized not in FEATURE_CLASS_RULES:
        raise ConfigurationError("{} has unsupported feature-class rule {}.".format(context, value))
    return FeatureClassRuleName(normalized)


def _field_rule_name(value: str, context: str) -> FieldRuleName:
    """Validate and convert a field rule name.

    Args:
        value: Rule text from CSV.
        context: CSV location for errors.

    Returns:
        FieldRuleName enum member.

    Raises:
        ConfigurationError: If the rule is unsupported.

    Notes:
        Constants remain the source of truth for supported values.
    """
    normalized = value.strip().upper()
    if normalized not in FIELD_RULES:
        raise ConfigurationError("{} has unsupported field rule {}.".format(context, value))
    return FieldRuleName(normalized)


def _geometry_rule_name(value: str, context: str) -> GeometryRuleName:
    """Validate and convert a geometry rule name.

    Args:
        value: Geometry rule text from CSV.
        context: CSV location for errors.

    Returns:
        GeometryRuleName enum member.

    Raises:
        ConfigurationError: If the geometry rule is unsupported.

    Notes:
        A blank source value is normalized by the caller to KEEP.
    """
    normalized = value.strip().upper()
    if normalized not in GEOMETRY_RULES:
        raise ConfigurationError("{} has unsupported geometry rule {}.".format(context, value))
    return GeometryRuleName(normalized)


__all__ = [
    "DomainRule", "FeatureClassRule", "FeatureClassRuleName", "FieldRule",
    "FieldRuleName", "GeometryRuleName", "LookupColumnRule",
    "LookupConfigurationRule", "LookupRule", "RuleSet", "load_configuration",
    "load_domain_rules", "load_feature_class_rules", "load_field_rules",
    "load_lookup_rules",
]
