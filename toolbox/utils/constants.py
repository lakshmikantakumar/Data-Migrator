"""Shared constants for the Geodatabase Migration Framework (GMF)."""

from __future__ import annotations

from typing import Final, FrozenSet, Tuple

FRAMEWORK_NAME: Final[str] = "Geodatabase Migration Framework"
FRAMEWORK_ALIAS: Final[str] = "GMF"
FRAMEWORK_VERSION: Final[str] = "1.0.0"
ARCGIS_PRO_VERSION: Final[str] = "3.x"

LOG_FOLDER_NAME: Final[str] = "logs"
REPORT_FOLDER_NAME: Final[str] = "reports"
MIGRATION_LOG_FILE: Final[str] = "Migration.log"

# CSV reports produced by report.py.  Utilities only name the artifacts; they
# never generate report content or apply reporting business rules.
VALIDATION_REPORT_FILE: Final[str] = "Validation_Report.csv"
MIGRATION_SUMMARY_REPORT_FILE: Final[str] = "Migration_Summary.csv"
FEATURE_CLASS_REPORT_FILE: Final[str] = "FeatureClass_Report.csv"
FIELD_REPORT_FILE: Final[str] = "Field_Report.csv"
DOMAIN_REPORT_FILE: Final[str] = "Domain_Report.csv"
ERROR_REPORT_FILE: Final[str] = "Error_Report.csv"
WARNING_REPORT_FILE: Final[str] = "Warning_Report.csv"
AUDIT_REPORT_FILE: Final[str] = "Audit_Report.csv"
REPORT_FILE_NAMES: Final[Tuple[str, ...]] = (
    VALIDATION_REPORT_FILE, MIGRATION_SUMMARY_REPORT_FILE,
    FEATURE_CLASS_REPORT_FILE, FIELD_REPORT_FILE, DOMAIN_REPORT_FILE,
    ERROR_REPORT_FILE, WARNING_REPORT_FILE, AUDIT_REPORT_FILE,
)

FC_MAPPING_FILE: Final[str] = "FC_Mapping.csv"
FIELD_MAPPING_FILE: Final[str] = "Field_Mapping.csv"
DOMAIN_MAPPING_FILE: Final[str] = "Domain_Mapping.csv"
LOOKUP_FILE: Final[str] = "Lookup.csv"
REQUIRED_CONFIGURATION_FILES: Final[Tuple[str, ...]] = (
    FC_MAPPING_FILE, FIELD_MAPPING_FILE, DOMAIN_MAPPING_FILE, LOOKUP_FILE,
)

# Common configuration columns.  Specific CSV validators compose these names
# as appropriate instead of scattering string literals through the framework.
CSV_SOURCE_GDB: Final[str] = "Source_GDB"
CSV_TARGET_GDB: Final[str] = "Target_GDB"
CSV_SOURCE_DATASET: Final[str] = "Source_Dataset"
CSV_TARGET_DATASET: Final[str] = "Target_Dataset"
CSV_SOURCE_FEATURE_CLASS: Final[str] = "Source_FeatureClass"
CSV_TARGET_FEATURE_CLASS: Final[str] = "Target_FeatureClass"
CSV_SOURCE_FIELD: Final[str] = "Source_Field"
CSV_TARGET_FIELD: Final[str] = "Target_Field"
CSV_RULE: Final[str] = "Rule"
CSV_GEOMETRY_RULE: Final[str] = "Geometry_Rule"
CSV_DEFAULT_VALUE: Final[str] = "Default_Value"
CSV_EXPRESSION: Final[str] = "Expression"
CSV_DOMAIN: Final[str] = "Domain"
CSV_LOOKUP_KEY: Final[str] = "Lookup_Key"
CSV_LOOKUP_VALUE: Final[str] = "Lookup_Value"

# Global operational defaults.  Values are configuration defaults, not paths
# hard-coded to a particular machine or geodatabase.
DEFAULT_TEXT_ENCODING: Final[str] = "utf-8-sig"
DEFAULT_PROGRESS_LABEL: Final[str] = "Processing migration"
DEFAULT_LOG_SEPARATOR_WIDTH: Final[int] = 80
DEFAULT_OVERWRITE_OUTPUT: Final[bool] = False
DEFAULT_ADD_OUTPUTS_TO_MAP: Final[bool] = False

LOG_INFO: Final[str] = "INFO"
LOG_WARNING: Final[str] = "WARNING"
LOG_ERROR: Final[str] = "ERROR"
LOG_CRITICAL: Final[str] = "CRITICAL"
LOG_LEVELS: Final[FrozenSet[str]] = frozenset((LOG_INFO, LOG_WARNING, LOG_ERROR, LOG_CRITICAL))

MODE_VALIDATE_ONLY: Final[str] = "Validate Only"
MODE_MIGRATE_ONLY: Final[str] = "Migrate Only"
MODE_VALIDATE_AND_MIGRATE: Final[str] = "Validate + Migrate"
MODE_GENERATE_REPORT: Final[str] = "Generate Report"
EXECUTION_MODES: Final[Tuple[str, ...]] = (
    MODE_VALIDATE_ONLY, MODE_MIGRATE_ONLY, MODE_VALIDATE_AND_MIGRATE, MODE_GENERATE_REPORT,
)

FC_RULE_COPY: Final[str] = "COPY"
FC_RULE_SPLIT: Final[str] = "SPLIT"
FC_RULE_MERGE: Final[str] = "MERGE"
FC_RULE_IGNORE: Final[str] = "IGNORE"
FC_RULE_EMPTY: Final[str] = "EMPTY"
FEATURE_CLASS_RULES: Final[FrozenSet[str]] = frozenset((FC_RULE_COPY, FC_RULE_SPLIT, FC_RULE_MERGE, FC_RULE_IGNORE, FC_RULE_EMPTY))

FIELD_RULE_COPY: Final[str] = "COPY"
FIELD_RULE_DOMAIN: Final[str] = "DOMAIN"
FIELD_RULE_DEFAULT: Final[str] = "DEFAULT"
FIELD_RULE_UUID: Final[str] = "UUID"
FIELD_RULE_LOOKUP: Final[str] = "LOOKUP"
FIELD_RULE_EXPRESSION: Final[str] = "EXPRESSION"
FIELD_RULE_CONCAT: Final[str] = "CONCAT"
FIELD_RULE_SPLIT: Final[str] = "SPLIT"
FIELD_RULE_SUBSTRING: Final[str] = "SUBSTRING"
FIELD_RULE_DATEFORMAT: Final[str] = "DATEFORMAT"
FIELD_RULE_CALCULATE: Final[str] = "CALCULATE"
FIELD_RULE_IGNORE: Final[str] = "IGNORE"
FIELD_RULES: Final[FrozenSet[str]] = frozenset((FIELD_RULE_COPY, FIELD_RULE_DOMAIN, FIELD_RULE_DEFAULT, FIELD_RULE_UUID, FIELD_RULE_LOOKUP, FIELD_RULE_EXPRESSION, FIELD_RULE_CONCAT, FIELD_RULE_SPLIT, FIELD_RULE_SUBSTRING, FIELD_RULE_DATEFORMAT, FIELD_RULE_CALCULATE, FIELD_RULE_IGNORE))

GEOMETRY_KEEP: Final[str] = "KEEP"
GEOMETRY_SINGLEPART: Final[str] = "SINGLEPART"
GEOMETRY_CENTROID: Final[str] = "CENTROID"
GEOMETRY_BOUNDARY: Final[str] = "BOUNDARY"
GEOMETRY_BUFFER: Final[str] = "BUFFER"
GEOMETRY_PROJECT: Final[str] = "PROJECT"
GEOMETRY_RULES: Final[FrozenSet[str]] = frozenset((GEOMETRY_KEEP, GEOMETRY_SINGLEPART, GEOMETRY_CENTROID, GEOMETRY_BOUNDARY, GEOMETRY_BUFFER, GEOMETRY_PROJECT))
SUPPORTED_GEOMETRY_TYPES: Final[FrozenSet[str]] = frozenset(("Point", "Multipoint", "Polyline", "Polygon"))

CSV_ENCODING: Final[str] = DEFAULT_TEXT_ENCODING
TIMESTAMP_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"
FILE_TIMESTAMP_FORMAT: Final[str] = "%Y%m%d_%H%M%S"

__all__ = [name for name in globals() if name.isupper()]
