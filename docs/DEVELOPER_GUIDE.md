# Developer Guide

## Development principles

- Target ArcGIS Pro 3.x and its supplied Python runtime.
- Use ArcPy and the Python standard library only.
- Add Google-style docstrings and type hints to public APIs.
- Keep target schema immutable: no create/delete/alter field, feature class,
  feature dataset, or domain operations.
- Use `SearchCursor` and `InsertCursor`; never introduce `UpdateCursor`.
- Do not alter global `arcpy.env.workspace`.

## Local checks

From the repository root, run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python -m compileall -q toolbox tests
git diff --check
```

Automated tests mock ArcPy. Before merging any ArcPy integration change, use a
disposable file GDB in ArcGIS Pro.

## Adding a field transformation

1. Add the rule name to `rules.py` when necessary.
2. Implement a dedicated `FieldTransformer` subclass in `transform.py`.
3. Register it in `TransformEngine`.
4. Validate parameters and source/target field requirements.
5. Add unit and migration tests.
6. Update CSV documentation and release notes.

The expression evaluator intentionally uses a restricted AST; do not replace it
with unrestricted `eval`.

## ArcPy changes and release discipline

Route ArcPy calls through `utils/arcpy_utils.py`, convert failures to custom
framework exceptions, and use explicit catalog paths. Every ArcPy addition
needs a mock-based unit test, ArcGIS Pro smoke-test procedure, error/reporting
path, and documented permission/license requirement. See the
[Software Quality Report](SOFTWARE_QUALITY_REPORT.md) for release recommendations.
