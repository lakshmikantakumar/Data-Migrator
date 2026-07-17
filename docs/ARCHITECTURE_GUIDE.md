# Architecture Guide

## Workflow

```text
ArcGIS Pro Toolbox (.pyt)
          |
          v
 Transformer controller
   |      |       |       \
 Rules  Validator Migrator Reports
   |       |         |
   +-------+---------+
           |
       utils package
           |
         ArcPy
```

The controller owns the workflow. It initializes logging, loads typed rules,
validates inputs, copies the template GDB when required, streams migration,
generates CSV reports, and returns an immutable final result.

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `Transformer.pyt` | ArcGIS Pro parameter UI and final geoprocessing status. |
| `transformer.py` | Lifecycle orchestration and execution result. |
| `rules.py` | CSV parsing and immutable typed rule objects. |
| `validator.py` | Read-only preflight checks and validation summary. |
| `migrator.py` | Cursor-based feature-class streaming and statistics. |
| `transform.py` | One class per field transformation rule. |
| `report.py` | CSV artifact creation. |
| `logger.py` | Thread-safe file/ArcGIS message logging. |
| `utils/` | Constants, ArcPy wrappers, GDB metadata, file, time, progress, and exception helpers. |

## Core design decisions

- **Template-first schema:** the template is copied before migration. GMF does
  not create, delete, or alter target datasets, feature classes, fields, or
  domains.
- **Typed configuration:** rules are frozen dataclasses and enums, not raw
  dictionaries.
- **Streaming:** one source cursor row is transformed and inserted at a time.
- **Safe ArcPy boundary:** `arcpy_utils` converts ArcPy failures to framework
  exceptions and deliberately exposes SearchCursor and InsertCursor only.
- **Metadata cache:** run-local caching avoids duplicate `Describe` calls
  without retaining stale metadata across runs.
- **Testability:** ArcPy imports are optional until required, enabling unit
  tests outside ArcGIS Pro.

## Extension points and constraints

Add a field transformation by implementing `FieldTransformer` and registering
it in `TransformEngine`. Add geometry transformations only with matching
validation, spatial-reference handling, ArcPy integration tests, and clear
release notes. Do not use schema-altering geoprocessing tools or globally set
`arcpy.env.workspace`; use explicit catalog paths instead.
