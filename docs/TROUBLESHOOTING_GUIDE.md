# Troubleshooting Guide

## Configuration errors

### Required CSV file or column is missing

Ensure the Configuration Folder contains `FC_Mapping.csv`,
`Field_Mapping.csv`, `Domain_Mapping.csv`, and `Lookup.csv`. Compare headers
with the [CSV Specification](CSV_SPECIFICATION.md), do not rename required
columns, and save the file as UTF-8 CSV.

### Invalid rule name or boolean

Use documented rule names. For `Enabled`, use `Yes`/`No` or a supported boolean
equivalent. Check for hidden whitespace and Excel formula output.

## Geodatabase and schema errors

### Source or template GDB does not exist

Verify the path in ArcGIS Pro Catalog under the same account that runs GMF.
For enterprise GDBs, refresh the database connection and verify network/VPN
access.

### Feature class, field, or domain is missing

Mappings must reference existing source data and existing target template
schema. Correct the mapping or template; GMF will not create missing objects.

### Geometry, spatial reference, or SQL filter validation failed

For `KEEP`, use compatible source and target geometry/spatial reference. Test a
reported SQL expression in ArcGIS Pro **Select By Attributes** for the source
feature class; SQL syntax depends on the source workspace.

## Migration errors

### Output GDB already exists

Choose a new path or enable **Overwrite Output** only after confirming the GDB
is disposable. Never use the template as output.

### Rows fail during insert

Review `Error_Report.csv`, `Audit_Report.csv`, and `Migration.log`. Typical
causes are invalid domain values, missing mappings for required target fields,
incompatible value types, or short target text fields. Correct the data,
mapping, or template and rerun to a new output GDB.

### No records migrated

Check whether the rule is `IGNORE` or `EMPTY`, whether the SQL filter selects
zero rows, and whether all rows failed. Inspect feature-class statistics and
errors before treating an empty output as success.

## Logging and reports

Set **Generate Log** to true and ensure the output/report location is writable
when `Migration.log` is missing. Open reports as UTF-8 CSV; use Excel’s
Text/CSV import workflow when double-clicking produces incorrect encoding.

## Escalation information

Provide ArcGIS Pro version, execution mode, sanitized configuration files,
full ArcGIS messages, `Migration.log`, relevant report rows, and whether the
GDB is file or enterprise. Do not provide credentials or sensitive attributes.
