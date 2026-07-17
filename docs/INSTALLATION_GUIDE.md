# Installation Guide

## Prerequisites

- ArcGIS Pro 3.x.
- A licensed ArcGIS Pro user with read access to source/template GDBs and write
  access to the output parent folder.
- A local clone or approved deployment copy of this repository.
- No `pip install` step: GMF uses the Python standard library and ArcPy only.

## Install into an ArcGIS Pro project

1. Place the `toolbox` folder in a stable, readable project location.
2. Open the target ArcGIS Pro project.
3. In Catalog, right-click **Toolboxes** and select **Add Toolbox**.
4. Browse to `toolbox/Transformer.pyt` and add it.
5. Open **Geodatabase Migration** and verify the seven parameters appear.

Keep `Transformer.pyt`, `transformer.py`, and the other Python modules together
inside `toolbox`; the Python toolbox imports neighbouring modules at run time.

## Prepare configuration

1. Create a configuration folder, for example `D:\GMF\configs\ProjectA`.
2. Copy all four files from `configs/AMRUT`.
3. Edit them using the [CSV Specification](CSV_SPECIFICATION.md).
4. Run **Validate Only** before any migration.

## Deployment and permissions

Back up the deployed application files and project configuration before an
upgrade. Replace the application files as one versioned unit, refresh the
toolbox in ArcGIS Pro, then validate a non-production GDB pair.

| Location | Minimum permission |
| --- | --- |
| Source GDB | Read metadata and source feature classes. |
| Template GDB | Read metadata and copy the geodatabase. |
| Output parent folder | Create output GDB and report/log folders. |
| Existing Output GDB | Delete permission only if overwrite is enabled. |

For enterprise geodatabases, test database connections and schema-qualified
paths under the same account that will run the toolbox.
