# Release Notes

## 1.0.0 — Initial release candidate

### Included

- ArcGIS Pro Python toolbox with configuration, GDB, execution mode, logging,
  and overwrite parameters.
- Typed CSV rules for feature-class, field, domain, and lookup mappings.
- Read-only validation and `Validation_Report.csv`.
- Template-copy, cursor-based COPY, SPLIT, and MERGE migration.
- Field transformations: COPY, DOMAIN, DEFAULT, UUID, LOOKUP, EXPRESSION,
  CONCAT, SPLIT, SUBSTRING, DATEFORMAT, CALCULATE, and IGNORE.
- CSV migration, feature class, field, domain, warning, error, and audit
  reports; thread-safe logging; ArcGIS progress; typed exceptions; Describe
  caching; and standard-library unit tests.

### Important limitations

- Feature classes only: no tables, rasters, annotation, attachments,
  relationships, topology, or utility networks.
- Only `KEEP` geometry transfer is executable. `SINGLEPART`, `CENTROID`,
  `BOUNDARY`, `BUFFER`, and `PROJECT` are recognized but not implemented
  migration transformations.
- Automated tests mock ArcPy. A real ArcGIS Pro acceptance test is required
  before production use.

### Upgrade notes

Back up configuration folders and output GDBs before replacing application
files. Re-run **Validate Only** after every upgrade. Complete the release
recommendations in [Software Quality Report](SOFTWARE_QUALITY_REPORT.md) before
declaring production version 1.0.
