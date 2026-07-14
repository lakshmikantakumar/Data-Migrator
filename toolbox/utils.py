# =============================================================================
# Geodatabase Migration Framework (GMF)
# -----------------------------------------------------------------------------
# File        : utils.py
# Description : Common utility functions used throughout the framework.
#
# Author      : Dr. Lakshmi Kantakumar Neelamsetti
# Organization: Survey of India
#
# Version     : 1.0.0
# ArcGIS Pro  : 3.x
# Python      : 3.x
#
# -----------------------------------------------------------------------------
#
# PURPOSE
# -------
# This module provides reusable utility functions that are shared across all
# framework modules.
#
# The utilities include:
#
#   • Date & Time
#   • UUID Generation
#   • File and Folder Operations
#   • Geodatabase Helpers
#   • ArcPy Helpers
#   • Environment Management
#   • Progress Utilities
#   • String Utilities
#   • Validation Helpers
#
# NOTE
# ----
# This module should NEVER contain migration logic.
#
# =============================================================================

import os
import sys
import uuid
import shutil
import traceback
import time
from datetime import datetime
import math


import arcpy

# =============================================================================
# FRAMEWORK INFORMATION
# =============================================================================

FRAMEWORK_NAME = "Geodatabase Migration Framework"

FRAMEWORK_ALIAS = "GMF"

FRAMEWORK_VERSION = "1.0.0"

AUTHOR = "Dr. Lakshmi Kantakumar Neelamsetti"

ORGANIZATION = "Survey of India"

SUPPORTED_GEOMETRY = (
    "Point",
    "Multipoint",
    "Polyline",
    "Polygon"
)

# =============================================================================
# DEFAULT FILE NAMES
# =============================================================================

FC_MAPPING_FILE = "FC_Mapping.csv"

FIELD_MAPPING_FILE = "Field_Mapping.csv"

DOMAIN_MAPPING_FILE = "Domain_Mapping.csv"

LOOKUP_MAPPING_FILE = "Lookup.csv"

# =============================================================================
# REPORT FILES
# =============================================================================

REPORT_FOLDER = "Reports"

LOG_FOLDER = "Logs"

MIGRATION_LOG = "Migration.log"

VALIDATION_REPORT = "Validation_Report.csv"

MIGRATION_REPORT = "Migration_Summary.csv"

FEATURECLASS_REPORT = "FeatureClass_Report.csv"

FIELD_REPORT = "Field_Report.csv"

DOMAIN_REPORT = "Domain_Report.csv"

ERROR_REPORT = "Error_Report.csv"

WARNING_REPORT = "Warning_Report.csv"

AUDIT_REPORT = "Audit_Report.csv"

# =============================================================================
# EXECUTION MODES
# =============================================================================

MODE_VALIDATE = "Validate Only"

MODE_MIGRATE = "Migrate Only"

MODE_VALIDATE_MIGRATE = "Validate + Migrate"

MODE_REPORT = "Generate Report"

# =============================================================================
# LOG LEVELS
# =============================================================================

LOG_INFO = "INFO"

LOG_WARNING = "WARNING"

LOG_ERROR = "ERROR"

LOG_CRITICAL = "CRITICAL"

# =============================================================================
# COMMON RULES
# =============================================================================

# Feature Class Rules

FC_RULE_COPY = "COPY"

FC_RULE_SPLIT = "SPLIT"

FC_RULE_MERGE = "MERGE"

FC_RULE_IGNORE = "IGNORE"

FC_RULE_EMPTY = "EMPTY"

# Geometry Rules

GEOM_KEEP = "KEEP"

GEOM_SINGLEPART = "SINGLEPART"

GEOM_CENTROID = "CENTROID"

GEOM_BOUNDARY = "BOUNDARY"

GEOM_BUFFER = "BUFFER"

GEOM_PROJECT = "PROJECT"

# Field Rules

RULE_COPY = "COPY"

RULE_DOMAIN = "DOMAIN"

RULE_DEFAULT = "DEFAULT"

RULE_UUID = "UUID"

RULE_LOOKUP = "LOOKUP"

RULE_EXPRESSION = "EXPRESSION"

RULE_CONCAT = "CONCAT"

RULE_SPLIT = "SPLIT"

RULE_SUBSTRING = "SUBSTRING"

RULE_DATEFORMAT = "DATEFORMAT"

RULE_CALCULATE = "CALCULATE"

RULE_IGNORE = "IGNORE"

# =============================================================================
# COMMON DATE FUNCTIONS
# =============================================================================

def get_current_datetime():
    """
    Returns the current date and time.

    Returns
    -------
    datetime
        Current system date and time.
    """
    return datetime.now()


def get_timestamp():
    """
    Returns a timestamp suitable for log and report file names.

    Example
    -------
    20260715_143521

    Returns
    -------
    str
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_date():
    """
    Returns today's date.

    Returns
    -------
    str

    Example
    -------
    2026-07-15
    """
    return datetime.now().strftime("%Y-%m-%d")


# =============================================================================
# UUID UTILITIES
# =============================================================================

def generate_uuid():
    """
    Generate a new UUID string.

    Returns
    -------
    str

    Example
    -------
    {6D2B64F4-47C5-4AE5-B1E7-89F78F4A0A84}
    """
    return "{" + str(uuid.uuid4()).upper() + "}"


# =============================================================================
# MESSAGE UTILITIES
# =============================================================================

def add_message(message):
    """
    Send an informational message to ArcGIS Pro and the Python console.

    Parameters
    ----------
    message : str
        Message to display.
    """
    arcpy.AddMessage(message)
    print(message)


def add_warning(message):
    """
    Send a warning message.

    Parameters
    ----------
    message : str
    """
    arcpy.AddWarning(message)
    print("WARNING :", message)


def add_error(message):
    """
    Send an error message.

    Parameters
    ----------
    message : str
    """
    arcpy.AddError(message)
    print("ERROR :", message)


# =============================================================================
# FRAMEWORK HEADER
# =============================================================================

def print_framework_header():
    """
    Print the framework banner.
    """

    add_message("=" * 70)
    add_message(FRAMEWORK_NAME)
    add_message("Version      : {}".format(FRAMEWORK_VERSION))
    add_message("Author       : {}".format(AUTHOR))
    add_message("Organization : {}".format(ORGANIZATION))
    add_message("=" * 70)


# =============================================================================
# ENVIRONMENT UTILITIES
# =============================================================================

def set_arcpy_environment(overwrite_output=False):
    """
    Configure ArcPy environment settings.

    Parameters
    ----------
    overwrite_output : bool
        Whether existing outputs can be overwritten.
    """

    arcpy.env.overwriteOutput = overwrite_output

    arcpy.env.addOutputsToMap = False

    arcpy.env.parallelProcessingFactor = "100%"


def reset_environment():
    """
    Reset ArcPy environments to defaults.
    """
    arcpy.ResetEnvironments()


# =============================================================================
# FILE AND FOLDER UTILITIES
# =============================================================================

def file_exists(file_path):
    """
    Check whether a file exists.

    Parameters
    ----------
    file_path : str

    Returns
    -------
    bool
    """

    return os.path.isfile(file_path)


def folder_exists(folder_path):
    """
    Check whether a folder exists.

    Parameters
    ----------
    folder_path : str

    Returns
    -------
    bool
    """

    return os.path.isdir(folder_path)


def create_folder(folder_path):
    """
    Create folder if it does not already exist.

    Parameters
    ----------
    folder_path : str

    Returns
    -------
    str
    """

    if not folder_exists(folder_path):
        os.makedirs(folder_path)

    return folder_path


def delete_file(file_path):
    """
    Delete a file if it exists.

    Parameters
    ----------
    file_path : str
    """

    if os.path.isfile(file_path):
        os.remove(file_path)


def delete_folder(folder_path):
    """
    Delete a folder and all its contents.

    Parameters
    ----------
    folder_path : str
    """

    if os.path.isdir(folder_path):
        shutil.rmtree(folder_path)


# =============================================================================
# PATH UTILITIES
# =============================================================================

def join_path(*paths):
    """
    Join multiple path components.

    Example
    -------
    join_path(root,"Logs","Migration.log")

    Returns
    -------
    str
    """

    return os.path.join(*paths)


def get_filename(path):
    """
    Return filename without extension.
    """

    return os.path.splitext(os.path.basename(path))[0]


def get_extension(path):
    """
    Return file extension.
    """

    return os.path.splitext(path)[1]


# =============================================================================
# GEODATABASE UTILITIES
# =============================================================================

def gdb_exists(gdb_path):
    """
    Check whether a geodatabase exists.

    Parameters
    ----------
    gdb_path : str

    Returns
    -------
    bool
    """

    return arcpy.Exists(gdb_path)


def copy_template_gdb(template_gdb, output_gdb, overwrite=False):
    """
    Copy Template GDB to Output GDB.

    Parameters
    ----------
    template_gdb : str

    output_gdb : str

    overwrite : bool

    Returns
    -------
    bool
    """

    try:

        if arcpy.Exists(output_gdb):

            if overwrite:

                add_warning("Deleting existing Output GDB...")

                arcpy.management.Delete(output_gdb)

            else:

                raise Exception(
                    "Output Geodatabase already exists."
                )

        add_message("Copying Template Geodatabase...")

        parent = os.path.dirname(output_gdb)

        name = os.path.basename(output_gdb)

        arcpy.management.Copy(template_gdb,
                              os.path.join(parent, name))

        return True

    except Exception as ex:

        add_error(str(ex))

        return False


# =============================================================================
# DATASET UTILITIES
# =============================================================================

def dataset_exists(gdb, dataset_name):
    """
    Check whether Feature Dataset exists.

    Parameters
    ----------
    gdb : str

    dataset_name : str

    Returns
    -------
    bool
    """

    path = os.path.join(gdb, dataset_name)

    return arcpy.Exists(path)


# =============================================================================
# FEATURE CLASS UTILITIES
# =============================================================================

def feature_class_exists(workspace, fc_name):
    """
    Check whether Feature Class exists.

    Parameters
    ----------
    workspace : str

    fc_name : str

    Returns
    -------
    bool
    """

    path = os.path.join(workspace, fc_name)

    return arcpy.Exists(path)


def get_feature_class_path(workspace, dataset, feature_class):
    """
    Build Feature Class path.

    Parameters
    ----------
    workspace : str

    dataset : str

    feature_class : str

    Returns
    -------
    str
    """

    if dataset:

        return os.path.join(workspace,
                            dataset,
                            feature_class)

    return os.path.join(workspace,
                        feature_class)


def list_feature_classes(workspace):
    """
    List all Feature Classes.

    Parameters
    ----------
    workspace : str

    Returns
    -------
    list
    """

    arcpy.env.workspace = workspace

    fc_list = []

    datasets = arcpy.ListDatasets("", "Feature")

    if datasets:

        for ds in datasets:

            for fc in arcpy.ListFeatureClasses(feature_dataset=ds):

                fc_list.append(os.path.join(ds, fc))

    for fc in arcpy.ListFeatureClasses():

        fc_list.append(fc)

    return sorted(fc_list)


# =============================================================================
# FIELD UTILITIES
# =============================================================================

def field_exists(feature_class,
                 field_name):
    """
    Check whether field exists.

    Parameters
    ----------
    feature_class : str

    field_name : str

    Returns
    -------
    bool
    """

    fields = arcpy.ListFields(feature_class)

    for field in fields:

        if field.name.upper() == field_name.upper():

            return True

    return False


def get_field(feature_class,
              field_name):
    """
    Return ArcPy Field object.

    Returns
    -------
    arcpy.Field

    None
    """

    fields = arcpy.ListFields(feature_class)

    for field in fields:

        if field.name.upper() == field_name.upper():

            return field

    return None


def list_fields(feature_class):
    """
    Return field names.

    Returns
    -------
    list
    """

    return [f.name for f in arcpy.ListFields(feature_class)]


# =============================================================================
# DOMAIN UTILITIES
# =============================================================================

def domain_exists(workspace,
                  domain_name):
    """
    Check whether domain exists.

    Parameters
    ----------
    workspace : str

    domain_name : str

    Returns
    -------
    bool
    """

    domains = arcpy.da.ListDomains(workspace)

    for domain in domains:

        if domain.name.upper() == domain_name.upper():

            return True

    return False


# =============================================================================
# CSV UTILITIES
# =============================================================================

def configuration_file(configuration_folder,
                       filename):
    """
    Return full path of configuration CSV.

    Parameters
    ----------
    configuration_folder : str

    filename : str

    Returns
    -------
    str
    """

    return os.path.join(configuration_folder,
                        filename)


def configuration_exists(configuration_folder,
                         filename):
    """
    Check whether configuration CSV exists.

    Returns
    -------
    bool
    """

    return file_exists(configuration_file(configuration_folder,
                                          filename))


# =============================================================================
# WORKSPACE INFORMATION
# =============================================================================

def workspace_exists(workspace):
    """
    Check whether a workspace (File GDB / Enterprise GDB) exists.

    Parameters
    ----------
    workspace : str

    Returns
    -------
    bool
    """

    return arcpy.Exists(workspace)


def workspace_type(workspace):
    """
    Returns workspace type.

    Returns
    -------
    str

    Example
    -------
    LocalDatabase
    RemoteDatabase
    FileSystem
    """

    desc = arcpy.Describe(workspace)

    return desc.workspaceType


def workspace_name(workspace):
    """
    Returns workspace name.

    Example
    -------
    Sample.gdb
    """

    return os.path.basename(workspace)


# =============================================================================
# DATASET FUNCTIONS
# =============================================================================

def dataset_exists(workspace,
                   dataset):
    """
    Check Feature Dataset exists.
    """

    path = os.path.join(workspace,
                        dataset)

    return arcpy.Exists(path)


def list_datasets(workspace):
    """
    List Feature Datasets.

    Parameters
    ----------
    workspace : str

    Returns
    -------
    list
    """

    old_workspace = arcpy.env.workspace

    arcpy.env.workspace = workspace

    datasets = arcpy.ListDatasets("", "Feature")

    arcpy.env.workspace = old_workspace

    if datasets is None:
        return []

    return sorted(datasets)


# =============================================================================
# FEATURE CLASS FUNCTIONS
# =============================================================================

def feature_class_exists(workspace,
                         dataset,
                         feature_class):
    """
    Check Feature Class exists.

    Parameters
    ----------
    workspace : str

    dataset : str

    feature_class : str

    Returns
    -------
    bool
    """

    fc = get_feature_class_path(workspace,
                                dataset,
                                feature_class)

    return arcpy.Exists(fc)


def get_feature_class_path(workspace,
                           dataset,
                           feature_class):
    """
    Construct full Feature Class path.

    Returns
    -------
    str
    """

    if dataset:

        return os.path.join(workspace,
                            dataset,
                            feature_class)

    return os.path.join(workspace,
                        feature_class)


def list_feature_classes(workspace):
    """
    List all Feature Classes.

    Includes root Feature Classes and those
    inside Feature Datasets.

    Parameters
    ----------
    workspace : str

    Returns
    -------
    list
    """

    old_workspace = arcpy.env.workspace

    arcpy.env.workspace = workspace

    fc_list = []

    # Root Feature Classes

    root_fc = arcpy.ListFeatureClasses()

    if root_fc:

        fc_list.extend(root_fc)

    # Dataset Feature Classes

    datasets = arcpy.ListDatasets("", "Feature")

    if datasets:

        for ds in datasets:

            fcs = arcpy.ListFeatureClasses(feature_dataset=ds)

            if fcs:

                for fc in fcs:

                    fc_list.append(os.path.join(ds, fc))

    arcpy.env.workspace = old_workspace

    return sorted(fc_list)


# =============================================================================
# FEATURE CLASS INFORMATION
# =============================================================================

def describe_feature_class(feature_class):
    """
    Returns Describe object.
    """

    return arcpy.Describe(feature_class)


def geometry_type(feature_class):
    """
    Return Geometry Type.

    Returns
    -------
    Point

    Multipoint

    Polyline

    Polygon
    """

    desc = arcpy.Describe(feature_class)

    return desc.shapeType


def spatial_reference(feature_class):
    """
    Return Spatial Reference object.
    """

    desc = arcpy.Describe(feature_class)

    return desc.spatialReference


def spatial_reference_name(feature_class):
    """
    Return Spatial Reference name.
    """

    sr = spatial_reference(feature_class)

    return sr.name


def has_z(feature_class):
    """
    Check Z enabled.
    """

    desc = arcpy.Describe(feature_class)

    return desc.hasZ


def has_m(feature_class):
    """
    Check M enabled.
    """

    desc = arcpy.Describe(feature_class)

    return desc.hasM


def objectid_field(feature_class):
    """
    Return ObjectID field.
    """

    desc = arcpy.Describe(feature_class)

    return desc.OIDFieldName


def shape_field(feature_class):
    """
    Return Shape field.
    """

    desc = arcpy.Describe(feature_class)

    return desc.shapeFieldName


def feature_count(feature_class):
    """
    Return Feature Count.

    Returns
    -------
    int
    """

    result = arcpy.management.GetCount(feature_class)

    return int(result[0])


# =============================================================================
# FIELD FUNCTIONS
# =============================================================================

def list_fields(feature_class):
    """
    Return list of ArcPy Field objects.
    """

    return arcpy.ListFields(feature_class)


def list_field_names(feature_class):
    """
    Return list of field names.
    """

    return [f.name for f in arcpy.ListFields(feature_class)]


def field_exists(feature_class,
                 field_name):
    """
    Check Field exists.
    """

    fields = arcpy.ListFields(feature_class,
                              field_name)

    return len(fields) > 0


def get_field(feature_class,
              field_name):
    """
    Return ArcPy Field object.

    Returns
    -------
    arcpy.Field

    None
    """

    fields = arcpy.ListFields(feature_class,
                              field_name)

    if len(fields) == 0:

        return None

    return fields[0]


def required_fields(feature_class):
    """
    Return required fields.
    """

    return [f.name
            for f in arcpy.ListFields(feature_class)
            if f.required]


def editable_fields(feature_class):
    """
    Return editable fields.
    """

    return [f.name
            for f in arcpy.ListFields(feature_class)
            if f.editable]


# =============================================================================
# DOMAIN FUNCTIONS
# =============================================================================

def list_domains(workspace):
    """
    Return list of Domains.
    """

    return arcpy.da.ListDomains(workspace)


def domain_exists(workspace,
                  domain_name):
    """
    Check Domain exists.
    """

    domains = arcpy.da.ListDomains(workspace)

    for domain in domains:

        if domain.name.upper() == domain_name.upper():

            return True

    return False


def get_domain(workspace,
               domain_name):
    """
    Return Domain object.
    """

    domains = arcpy.da.ListDomains(workspace)

    for domain in domains:

        if domain.name.upper() == domain_name.upper():

            return domain

    return None


# =============================================================================
# GEOMETRY COMPATIBILITY
# =============================================================================

def geometry_compatible(source_fc,
                        target_fc):
    """
    Check whether two Feature Classes have
    compatible geometry.

    Returns
    -------
    bool
    """

    return geometry_type(source_fc) == geometry_type(target_fc)


def spatial_reference_compatible(source_fc,
                                 target_fc):
    """
    Compare Spatial References.

    Returns
    -------
    bool
    """

    sr1 = spatial_reference(source_fc)

    sr2 = spatial_reference(target_fc)

    return sr1.factoryCode == sr2.factoryCode

# =============================================================================
# SECTION 4
# PROGRESS, TIMING & FORMATTING UTILITIES
# =============================================================================

# =============================================================================
# TIMER FUNCTIONS
# =============================================================================

def start_timer():
    """
    Start a timer.

    Returns
    -------
    float
        Current high-resolution timer.
    """
    return time.perf_counter()


def stop_timer(start_time):
    """
    Return elapsed time in seconds.

    Parameters
    ----------
    start_time : float

    Returns
    -------
    float
    """

    return round(time.perf_counter() - start_time, 3)


def elapsed_time(start_time):
    """
    Return elapsed time as HH:MM:SS.

    Parameters
    ----------
    start_time : float

    Returns
    -------
    str
    """

    seconds = int(time.perf_counter() - start_time)

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    return "{:02d}:{:02d}:{:02d}".format(
        hours,
        minutes,
        secs
    )


# =============================================================================
# NUMBER FORMATTING
# =============================================================================

def format_integer(value):
    """
    Format integer with comma separator.

    Example
    -------
    1250000

    becomes

    1,250,000
    """

    return "{:,}".format(int(value))


def format_float(value,
                 precision=2):
    """
    Format floating point number.

    Parameters
    ----------
    value : float

    precision : int

    Returns
    -------
    str
    """

    return "{:,.{}f}".format(
        float(value),
        precision
    )


def percentage(part,
               whole,
               precision=2):
    """
    Calculate percentage.

    Returns
    -------
    float
    """

    if whole == 0:

        return 0

    return round((part / whole) * 100,
                 precision)


# =============================================================================
# STRING UTILITIES
# =============================================================================

def repeat(character="-",
           count=80):
    """
    Return repeated character string.
    """

    return character * count


def center(text,
           width=80,
           fill="-"):
    """
    Center text.

    Example
    -------
    ---------- Migration ----------
    """

    return text.center(width,
                       fill)


def left(text,
         width=30):

    return str(text).ljust(width)


def right(text,
          width=30):

    return str(text).rjust(width)


# =============================================================================
# PROGRESS FUNCTIONS
# =============================================================================

def initialize_progress(total,
                        label="Processing..."):
    """
    Initialize ArcGIS progressor.

    Parameters
    ----------
    total : int

    label : str
    """

    arcpy.SetProgressor(
        "step",
        label,
        0,
        total,
        1
    )


def update_progress(position,
                    message=""):
    """
    Update ArcGIS progress bar.

    Parameters
    ----------
    position : int

    message : str
    """

    arcpy.SetProgressorLabel(message)

    arcpy.SetProgressorPosition(position)


def reset_progress():
    """
    Reset ArcGIS progressor.
    """

    arcpy.ResetProgressor()


# =============================================================================
# FEATURE CLASS PROGRESS
# =============================================================================

def progress_message(feature_class,
                     current,
                     total):
    """
    Return formatted progress message.

    Example
    -------
    Road : 12,520 / 24,380
    """

    return "{} : {} / {}".format(
        feature_class,
        format_integer(current),
        format_integer(total)
    )


# =============================================================================
# MIGRATION SUMMARY
# =============================================================================

def migration_summary(feature_class,
                      source_count,
                      migrated_count,
                      failed_count,
                      elapsed):
    """
    Return formatted migration summary.

    Returns
    -------
    dict
    """

    return {

        "FeatureClass": feature_class,

        "Source": source_count,

        "Migrated": migrated_count,

        "Failed": failed_count,

        "Elapsed": elapsed

    }


# =============================================================================
# VALIDATION SUMMARY
# =============================================================================

def validation_summary():

    return {

        "Passed": 0,

        "Warnings": 0,

        "Errors": 0

    }


# =============================================================================
# MEMORY (Future Use)
# =============================================================================

def bytes_to_mb(size):

    return round(size / (1024 * 1024), 2)


def bytes_to_gb(size):

    return round(size / (1024 * 1024 * 1024), 2)


# =============================================================================
# SAFE DIVISION
# =============================================================================

def safe_divide(a,
                b):
    """
    Divide safely.

    Returns
    -------
    float
    """

    if b == 0:

        return 0

    return a / b

# =============================================================================
# SECTION 5
# ARCPY UTILITIES & EXCEPTION HANDLING
# =============================================================================


# =============================================================================
# ARCPY MESSAGE FUNCTIONS
# =============================================================================

def add_info(message):
    """
    Display an informational message.

    Parameters
    ----------
    message : str
    """

    arcpy.AddMessage(str(message))


def add_warning(message):
    """
    Display a warning message.

    Parameters
    ----------
    message : str
    """

    arcpy.AddWarning(str(message))


def add_error(message):
    """
    Display an error message.

    Parameters
    ----------
    message : str
    """

    arcpy.AddError(str(message))


# =============================================================================
# ENVIRONMENT MANAGEMENT
# =============================================================================

def save_environment():
    """
    Save current ArcPy environment settings.

    Returns
    -------
    dict
    """

    env = {

        "workspace": arcpy.env.workspace,

        "scratchWorkspace": arcpy.env.scratchWorkspace,

        "overwriteOutput": arcpy.env.overwriteOutput,

        "parallelProcessingFactor":
            arcpy.env.parallelProcessingFactor,

        "outputCoordinateSystem":
            arcpy.env.outputCoordinateSystem

    }

    return env


def restore_environment(environment):
    """
    Restore ArcPy environment.

    Parameters
    ----------
    environment : dict
    """

    arcpy.env.workspace = environment["workspace"]

    arcpy.env.scratchWorkspace = environment["scratchWorkspace"]

    arcpy.env.overwriteOutput = environment["overwriteOutput"]

    arcpy.env.parallelProcessingFactor = \
        environment["parallelProcessingFactor"]

    arcpy.env.outputCoordinateSystem = \
        environment["outputCoordinateSystem"]


# =============================================================================
# DESCRIBE HELPERS
# =============================================================================

def describe(path):
    """
    Safe Describe wrapper.

    Parameters
    ----------
    path : str

    Returns
    -------
    arcpy.Describe
    """

    return arcpy.Describe(path)


def exists(path):
    """
    Wrapper for arcpy.Exists()

    Parameters
    ----------
    path : str

    Returns
    -------
    bool
    """

    return arcpy.Exists(path)


# =============================================================================
# GEOMETRY VALIDATION
# =============================================================================

def validate_geometry(source_fc,
                      target_fc):
    """
    Compare geometry types.

    Returns
    -------
    bool
    """

    source = describe(source_fc)

    target = describe(target_fc)

    return source.shapeType == target.shapeType


# =============================================================================
# SPATIAL REFERENCE VALIDATION
# =============================================================================

def validate_spatial_reference(source_fc,
                               target_fc):
    """
    Compare coordinate systems.

    Returns
    -------
    bool
    """

    sr1 = describe(source_fc).spatialReference

    sr2 = describe(target_fc).spatialReference

    return sr1.factoryCode == sr2.factoryCode


# =============================================================================
# FEATURE COUNT
# =============================================================================

def get_count(feature_class):
    """
    Return feature count.

    Parameters
    ----------
    feature_class : str

    Returns
    -------
    int
    """

    result = arcpy.management.GetCount(feature_class)

    return int(result[0])


# =============================================================================
# CURSOR HELPERS
# =============================================================================

def search_cursor(feature_class,
                  fields,
                  where_clause=None):
    """
    Create SearchCursor.

    Returns
    -------
    arcpy.da.SearchCursor
    """

    return arcpy.da.SearchCursor(
        feature_class,
        fields,
        where_clause
    )


def insert_cursor(feature_class,
                  fields):
    """
    Create InsertCursor.

    Returns
    -------
    arcpy.da.InsertCursor
    """

    return arcpy.da.InsertCursor(
        feature_class,
        fields
    )


def update_cursor(feature_class,
                  fields,
                  where_clause=None):
    """
    Create UpdateCursor.

    Returns
    -------
    arcpy.da.UpdateCursor
    """

    return arcpy.da.UpdateCursor(
        feature_class,
        fields,
        where_clause
    )


# =============================================================================
# TOOL EXECUTION
# =============================================================================

def execute_tool(tool_function,
                 *args,
                 **kwargs):
    """
    Execute ArcPy tool safely.

    Parameters
    ----------
    tool_function : callable

    Returns
    -------
    object
    """

    try:

        return tool_function(*args, **kwargs)

    except arcpy.ExecuteError:

        raise RuntimeError(arcpy.GetMessages(2))

    except Exception:

        raise


# =============================================================================
# ERROR INFORMATION
# =============================================================================

def get_python_traceback():
    """
    Return Python traceback.

    Returns
    -------
    str
    """

    return traceback.format_exc()


def get_arcpy_messages():
    """
    Return ArcPy messages.

    Returns
    -------
    str
    """

    return arcpy.GetMessages()


def get_arcpy_error_messages():
    """
    Return ArcPy error messages.

    Returns
    -------
    str
    """

    return arcpy.GetMessages(2)


# =============================================================================
# ERROR LOGGER
# =============================================================================

def log_exception(exception,
                  logger=None):
    """
    Log exception consistently.

    Parameters
    ----------
    exception : Exception

    logger : Logger
    """

    message = str(exception)

    traceback_text = traceback.format_exc()

    add_error(message)

    if logger:

        logger.error(message)

        logger.error(traceback_text)


# =============================================================================
# SAFE EXECUTION
# =============================================================================

def safe_execute(function,
                 *args,
                 **kwargs):
    """
    Execute any function safely.

    Returns
    -------
    tuple

    (success,
     result,
     error)
    """

    try:

        result = function(*args,
                          **kwargs)

        return True, result, None

    except Exception as ex:

        return False, None, ex


# =============================================================================
# VALIDATION RESULT
# =============================================================================

def validation_result(name,
                      passed,
                      message):
    """
    Create validation record.

    Returns
    -------
    dict
    """

    return {

        "Check": name,

        "Passed": passed,

        "Message": message

    }


# =============================================================================
# MIGRATION RESULT
# =============================================================================

def migration_result(feature_class,
                     source,
                     migrated,
                     skipped,
                     failed):
    """
    Create migration summary.

    Returns
    -------
    dict
    """

    return {

        "FeatureClass": feature_class,

        "Source": source,

        "Migrated": migrated,

        "Skipped": skipped,

        "Failed": failed

    }


# =============================================================================
# CLEANUP
# =============================================================================

def cleanup():
    """
    Reset ArcPy environment and progressor.
    """

    arcpy.ResetProgressor()

    arcpy.ResetEnvironments()


# =============================================================================
# END OF SECTION 5
# =============================================================================