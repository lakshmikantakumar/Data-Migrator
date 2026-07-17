"""Geodatabase inspection helpers that preserve the target template schema."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from . import arcpy_utils
from .constants import SUPPORTED_GEOMETRY_TYPES
from .exception_utils import MigrationError, ValidationError


class MetadataCache:
    """Cache ArcPy Describe results for the lifetime of one migration run.

    Args:
        None.

    Raises:
        None.

    Notes:
        Cache instances are deliberately local to a migration; metadata is not
        persisted because a geodatabase can change between runs.
    """

    def __init__(self) -> None:
        """Create an empty metadata cache.

        Args:
            None.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Keys are normalized absolute catalog paths.
        """
        self._descriptions: Dict[str, Any] = {}

    def describe(self, path: str) -> Any:
        """Return cached Describe metadata for a catalog path.

        Args:
            path: Catalog path to describe.

        Returns:
            ArcPy Describe result.

        Raises:
            MigrationError: If ArcPy cannot describe the path.

        Notes:
            The first request performs the ArcPy call; later requests reuse it.
        """
        key = _cache_key(path)
        if key not in self._descriptions:
            self._descriptions[key] = arcpy_utils.describe(path)
        return self._descriptions[key]

    def clear(self) -> None:
        """Remove all cached metadata.

        Args:
            None.

        Returns:
            None.

        Raises:
            None.

        Notes:
            Call after a migration run or when a source is intentionally reset.
        """
        self._descriptions.clear()


@dataclass(frozen=True)
class FeatureClassInfo:
    """Immutable metadata needed to validate a feature-class migration.

    Args:
        path: Feature class catalog path.
        name: ArcGIS feature class name.
        geometry_type: ArcGIS shape type.
        spatial_reference_name: Spatial-reference display name.
        spatial_reference_factory_code: Spatial-reference WKID when known.
        fields: Field metadata keyed by field name.

    Raises:
        None.

    Notes:
        This is read-only metadata; it cannot change source or target schema.
    """

    path: str
    name: str
    geometry_type: str
    spatial_reference_name: str
    spatial_reference_factory_code: Optional[int]
    fields: Mapping[str, Mapping[str, Any]]


def validate_geodatabase(workspace: str, label: str = "Geodatabase") -> None:
    """Validate that a workspace exists and is a local or enterprise database.

    Args:
        workspace: Geodatabase catalog path.
        label: Name used in validation messages.

    Returns:
        None.

    Raises:
        ValidationError: If the workspace is missing or has an unsupported
            ArcPy workspace type.

    Notes:
        File geodatabases and enterprise geodatabases are both accepted.
    """
    if not arcpy_utils.exists(workspace):
        raise ValidationError("{} does not exist: {}".format(label, workspace))
    description = arcpy_utils.describe(workspace)
    workspace_type = getattr(description, "workspaceType", "")
    if workspace_type not in {"LocalDatabase", "RemoteDatabase"}:
        raise ValidationError("{} is not a geodatabase workspace: {}".format(label, workspace))


def feature_class_path(workspace: str, dataset: Optional[str], feature_class: str) -> str:
    """Build a catalog path for a root or feature-dataset feature class.

    Args:
        workspace: Parent geodatabase path.
        dataset: Optional feature dataset name.
        feature_class: Feature class name.

    Returns:
        Joined catalog path.

    Raises:
        ValueError: If workspace or feature class name is empty.

    Notes:
        This function does not create any geodatabase objects.
    """
    if not workspace or not feature_class:
        raise ValueError("workspace and feature_class are required.")
    parts = [workspace, feature_class] if not dataset else [workspace, dataset, feature_class]
    return os.path.join(*parts)


def feature_dataset_exists(workspace: str, dataset: str) -> bool:
    """Return whether a named feature dataset exists in a workspace.

    Args:
        workspace: Parent geodatabase catalog path.
        dataset: Feature dataset name.

    Returns:
        ``True`` when ArcPy recognizes a FeatureDataset at the path.

    Raises:
        MigrationError: If ArcPy cannot inspect the dataset.

    Notes:
        This function only inspects metadata and never creates a dataset.
    """
    path = os.path.join(workspace, dataset)
    if not arcpy_utils.exists(path):
        return False
    return getattr(arcpy_utils.describe(path), "dataType", "") == "FeatureDataset"


def list_feature_datasets(workspace: str) -> List[str]:
    """List feature-dataset names without changing the ArcPy workspace.

    Args:
        workspace: Geodatabase to inspect.

    Returns:
        Sorted feature-dataset names.

    Raises:
        MigrationError: If ArcPy cannot enumerate datasets.

    Notes:
        da.Walk uses an explicit workspace and preserves global environments.
    """
    api = arcpy_utils.require_arcpy()
    try:
        datasets = []
        for directory, names, _ in api.da.Walk(workspace, datatype="FeatureDataset"):
            for name in names:
                datasets.append(os.path.relpath(os.path.join(directory, name), workspace))
        return sorted(datasets)
    except Exception as error:
        raise MigrationError("Listing feature datasets in {} failed: {}".format(workspace, error)) from error


def list_feature_classes(workspace: str) -> List[str]:
    """List root and feature-dataset feature classes without changing env.workspace.

    Args:
        workspace: Geodatabase to inspect.

    Returns:
        Sorted relative feature-class catalog paths.

    Raises:
        MigrationError: If ArcPy cannot enumerate the workspace.

    Notes:
        ArcPy's ``da.Walk`` accepts an explicit workspace and avoids global
        ``arcpy.env.workspace`` mutation.
    """
    api = arcpy_utils.require_arcpy()
    try:
        feature_classes: List[str] = []
        for directory, _, names in api.da.Walk(workspace, datatype="FeatureClass"):
            for name in names:
                feature_classes.append(os.path.relpath(os.path.join(directory, name), workspace))
        return sorted(feature_classes)
    except Exception as error:
        raise MigrationError("Listing feature classes in {} failed: {}".format(workspace, error)) from error


def validate_feature_class(feature_class: str, cache: Optional[MetadataCache] = None) -> Any:
    """Validate that a path is a supported feature class and return metadata.

    Args:
        feature_class: Feature class catalog path.
        cache: Optional metadata cache for repeated checks.

    Returns:
        ArcPy Describe metadata.

    Raises:
        ValidationError: If the object is missing or unsupported.

    Notes:
        Version 1.0 intentionally excludes tables, rasters, and annotation.
    """
    if not arcpy_utils.exists(feature_class):
        raise ValidationError("Feature class does not exist: {}".format(feature_class))
    description = cache.describe(feature_class) if cache else arcpy_utils.describe(feature_class)
    if getattr(description, "dataType", "") != "FeatureClass":
        raise ValidationError("Only Feature Classes are supported: {}".format(feature_class))
    shape_type = getattr(description, "shapeType", "")
    if shape_type not in SUPPORTED_GEOMETRY_TYPES:
        raise ValidationError("Unsupported feature class geometry {}: {}".format(shape_type, feature_class))
    return description


def list_field_names(feature_class: str) -> List[str]:
    """Return field names in ArcPy's source order.

    Args:
        feature_class: Feature class to inspect.

    Returns:
        Field-name list.

    Raises:
        MigrationError: If ArcPy cannot list fields.

    Notes:
        Field objects are not cached because callers generally require names.
    """
    api = arcpy_utils.require_arcpy()
    try:
        return [field.name for field in api.ListFields(feature_class)]
    except Exception as error:
        raise MigrationError("Listing fields for {} failed: {}".format(feature_class, error)) from error


def field_exists(feature_class: str, field_name: str) -> bool:
    """Return whether a feature class contains a named field.

    Args:
        feature_class: Feature class to inspect.
        field_name: Field name to find.

    Returns:
        ``True`` when a case-insensitive match exists.

    Raises:
        MigrationError: If ArcPy cannot list fields.

    Notes:
        ArcGIS field-name casing may vary by underlying geodatabase type.
    """
    return field_name.casefold() in {name.casefold() for name in list_field_names(feature_class)}


def field_information(feature_class: str) -> Dict[str, Dict[str, Any]]:
    """Return read-only field metadata keyed by each field name.

    Args:
        feature_class: Feature class to inspect.

    Returns:
        Mapping of ArcGIS field properties.

    Raises:
        MigrationError: If ArcPy cannot inspect fields.

    Notes:
        The result supports mapping validation without adding or deleting
        fields in the copied target schema.
    """
    api = arcpy_utils.require_arcpy()
    try:
        return {
            field.name: {
                "name": field.name, "type": field.type, "length": field.length,
                "nullable": field.isNullable, "required": field.required,
                "domain": field.domain, "default": field.defaultValue,
            }
            for field in api.ListFields(feature_class)
        }
    except Exception as error:
        raise MigrationError("Reading fields for {} failed: {}".format(feature_class, error)) from error


def geometry_type(feature_class: str, cache: Optional[MetadataCache] = None) -> str:
    """Return the ArcGIS geometry type of a validated feature class.

    Args:
        feature_class: Feature class to inspect.
        cache: Optional Describe cache.

    Returns:
        Geometry type, such as ``Point`` or ``Polygon``.

    Raises:
        ValidationError: If the feature class is unsupported.

    Notes:
        Version 1.0 permits only the GMF supported geometry types.
    """
    return getattr(validate_feature_class(feature_class, cache), "shapeType")


def spatial_reference_information(feature_class: str, cache: Optional[MetadataCache] = None) -> Dict[str, Any]:
    """Return read-only spatial-reference information for a feature class.

    Args:
        feature_class: Feature class to inspect.
        cache: Optional Describe cache.

    Returns:
        Spatial-reference name and factory code.

    Raises:
        ValidationError: If the feature class is unsupported.

    Notes:
        The value helps validate PROJECT geometry rules without editing schema.
    """
    reference = getattr(validate_feature_class(feature_class, cache), "spatialReference", None)
    return {
        "name": getattr(reference, "name", "Unknown"),
        "factory_code": getattr(reference, "factoryCode", None),
    }


def domain_information(workspace: str) -> Dict[str, Dict[str, Any]]:
    """Return existing geodatabase-domain metadata keyed by domain name.

    Args:
        workspace: Geodatabase containing domains.

    Returns:
        Mapping of existing domain properties.

    Raises:
        MigrationError: If ArcPy cannot list domains.

    Notes:
        Domains are inspected only; GMF never modifies them.
    """
    api = arcpy_utils.require_arcpy()
    try:
        return {
            domain.name: {
                "name": domain.name, "description": domain.description,
                "domain_type": domain.domainType, "field_type": domain.type,
                "coded_values": dict(domain.codedValues or {}),
            }
            for domain in api.da.ListDomains(workspace)
        }
    except Exception as error:
        raise MigrationError("Reading domains for {} failed: {}".format(workspace, error)) from error


def feature_class_information(feature_class: str, cache: Optional[MetadataCache] = None) -> FeatureClassInfo:
    """Build a FeatureClassInfo record from cached metadata and fields.

    Args:
        feature_class: Feature class to inspect.
        cache: Optional reusable Describe cache.

    Returns:
        Immutable FeatureClassInfo record.

    Raises:
        ValidationError: If the feature class is unsupported.
        MigrationError: If field information cannot be read.

    Notes:
        This is the preferred metadata entry point for migration validation.
    """
    description = validate_feature_class(feature_class, cache)
    spatial_reference = spatial_reference_information(feature_class, cache)
    return FeatureClassInfo(
        path=feature_class,
        name=getattr(description, "name", os.path.basename(feature_class)),
        geometry_type=getattr(description, "shapeType"),
        spatial_reference_name=str(spatial_reference["name"]),
        spatial_reference_factory_code=spatial_reference["factory_code"],
        fields=field_information(feature_class),
    )


def copy_template_geodatabase(template_gdb: str, output_gdb: str, overwrite: bool = False) -> str:
    """Copy a template geodatabase as the migration target schema.

    Args:
        template_gdb: Existing template geodatabase.
        output_gdb: New target geodatabase path.
        overwrite: Whether an existing output may be deleted by ArcPy.

    Returns:
        Output geodatabase path.

    Raises:
        ValidationError: If the template is invalid or output exists without
            explicit overwrite permission.
        MigrationError: If copy or requested deletion fails.

    Notes:
        This performs a geodatabase copy only; it never creates datasets,
        feature classes, fields, or domains.
    """
    validate_geodatabase(template_gdb, "Template geodatabase")
    api = arcpy_utils.require_arcpy()
    if arcpy_utils.exists(output_gdb):
        if not overwrite:
            raise ValidationError("Output geodatabase already exists: {}".format(output_gdb))
        arcpy_utils.execute(api.management.Delete, output_gdb, context="Deleting existing output geodatabase")
    parent, name = os.path.split(output_gdb)
    if not parent or not name:
        raise ValidationError("Output geodatabase must include a parent folder and name.")
    arcpy_utils.execute(api.management.Copy, template_gdb, output_gdb, context="Copying template geodatabase")
    return output_gdb


def _cache_key(path: str) -> str:
    """Produce a stable cache key for a catalog path.

    Args:
        path: Catalog path to normalize.

    Returns:
        Case-normalized absolute path string.

    Raises:
        None.

    Notes:
        ``normcase`` makes Windows catalog paths cache consistently.
    """
    return os.path.normcase(os.path.abspath(path))


__all__ = [
    "FeatureClassInfo", "MetadataCache", "copy_template_geodatabase",
    "domain_information", "feature_class_information", "feature_class_path",
    "feature_dataset_exists", "field_exists", "field_information", "geometry_type",
    "list_feature_classes", "list_feature_datasets", "list_field_names",
    "spatial_reference_information", "validate_feature_class", "validate_geodatabase",
]
