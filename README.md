# Geodatabase Migration Framework

GMF is an ArcGIS Pro Python toolbox for moving **feature-class data** from a
source geodatabase into a copy of a template geodatabase. CSV mapping files
define which feature classes and fields are migrated. The template is always
the authoritative target schema.

## What GMF does

- Validates configuration files, geodatabases, feature classes, fields,
  domains, SQL filters, geometry, and spatial references.
- Copies the template geodatabase before a migration.
- Streams source data with ArcPy `SearchCursor` and writes with `InsertCursor`.
- Transforms mapped fields and creates CSV audit reports.
- Writes ArcGIS geoprocessing messages and, when selected, `Migration.log`.

## Version 1.0 boundaries

- Supports only Point, Multipoint, Polyline, and Polygon feature classes.
- Does not support tables, rasters, annotation, dimensions, attachments,
  relationship classes, topology, or utility networks.
- Never creates or changes feature datasets, feature classes, fields, or
  domains. It only inserts data into the copied template schema.
- COPY, SPLIT, and MERGE feature-class rules currently migrate geometry only
  when `Geometry_Rule` is `KEEP`. Other configured geometry rules are
  validated but deliberately fail during migration until implemented.

## Quick start

1. Read [Installation Guide](docs/INSTALLATION_GUIDE.md).
2. Copy the four required CSV files from `configs/AMRUT` into a project
   configuration folder and edit them for the source and template schemas.
3. Add `toolbox/Transformer.pyt` to an ArcGIS Pro project.
4. Run **Geodatabase Migration** in **Validate Only** mode first.
5. Correct all validation errors, then use **Validate + Migrate**.
6. Review the generated reports and `Migration.log` before using the output.

## Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Installation Guide](docs/INSTALLATION_GUIDE.md)
- [CSV Specification](docs/CSV_SPECIFICATION.md)
- [Architecture Guide](docs/ARCHITECTURE_GUIDE.md)
- [Developer Guide](docs/DEVELOPER_GUIDE.md)
- [Troubleshooting Guide](docs/TROUBLESHOOTING_GUIDE.md)
- [Release Notes](docs/RELEASE_NOTES.md)
- [Software Quality Report](docs/SOFTWARE_QUALITY_REPORT.md)

## Required configuration files

Every configuration folder must contain exactly these files:

- `FC_Mapping.csv`
- `Field_Mapping.csv`
- `Domain_Mapping.csv`
- `Lookup.csv`

See the [CSV Specification](docs/CSV_SPECIFICATION.md) for required headers,
valid rule names, and examples.

## License and support

This repository does not currently include a license file or support policy.
Confirm ownership, data-governance, and operational-support arrangements before
using GMF with production enterprise geodatabases.
