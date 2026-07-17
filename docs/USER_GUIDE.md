# User Guide

## Purpose

Use GMF to validate and migrate feature-class records into a template-derived
output geodatabase. GMF is intended for GIS professionals who own the source
data, target template, and CSV mapping configuration.

## Before you begin

- Use ArcGIS Pro 3.x with access to the source and template geodatabases.
- Ensure the output location is writable and has sufficient free disk space.
- Confirm the template contains every target feature class, field, and domain
  required by the mappings.
- Back up the source, template, and any output GDB that could be overwritten.
- Prepare the four CSV files described in the [CSV Specification](CSV_SPECIFICATION.md).

## Add the toolbox

In the Catalog pane, right-click **Toolboxes**, choose **Add Toolbox**, and
select `toolbox/Transformer.pyt`. Expand the toolbox and open
**Geodatabase Migration**.

## Tool parameters

| Parameter | Required | Description |
| --- | --- | --- |
| Configuration Folder | Yes | Folder containing the four required CSV files. |
| Source GDB | Yes | Source file or enterprise geodatabase. |
| Template GDB | Yes | Schema-only reference to copy before migration. |
| Output GDB | Yes | New output GDB path; must differ from Template GDB. |
| Execution Mode | Yes | Validate Only, Migrate Only, Validate + Migrate, or Generate Report. |
| Generate Log | No | Creates `Migration.log`. Default: true. |
| Overwrite Output | No | Permits deleting an existing Output GDB. Default: false. |

## Execution modes

| Mode | Use it for | Behavior |
| --- | --- | --- |
| Validate Only | Safe preflight | Validates and writes `Validation_Report.csv`. |
| Migrate Only | Approved configuration | Copies the template and migrates without preflight. Use cautiously. |
| Validate + Migrate | Normal production run | Migrates only if validation has no errors. |
| Generate Report | Report-only workflow | Generates reports from controller run information. |

## Recommended workflow

1. Make a dated copy of the configuration folder.
2. Run **Validate Only** and inspect `Validation_Report.csv`.
3. Resolve every ERROR. Review every WARNING with the data owner.
4. Run **Validate + Migrate** to a new, empty output path.
5. Review `Migration_Summary.csv`, `Error_Report.csv`, `Warning_Report.csv`,
   and `Audit_Report.csv`.
6. Open representative output feature classes in ArcGIS Pro and compare counts,
   geometry, domains, and key attributes with the source.
7. Only then publish or hand over the output GDB.

## Outputs and safety

GMF creates CSV reports and, when selected, `Migration.log`. ArcGIS messages
appear in the Geoprocessing pane. Never select the template as output, only use
**Overwrite Output** for disposable GDBs, and use `Geometry_Rule=KEEP` for
executable v1.0 migrations. See [Troubleshooting Guide](TROUBLESHOOTING_GUIDE.md).
