# CSV Configuration Specification

## General rules

Configuration files are UTF-8 CSV files with a header row. Header matching is
case-insensitive; values are trimmed. Empty rows are ignored. Each configuration
folder must contain all four files even when a mapping type is not used.

`Enabled` accepts `Yes`/`No`, `True`/`False`, `1`/`0`, or equivalent boolean
values. Use `No` to preserve a row as documentation without processing it.

## FC_Mapping.csv

Required columns: `Enabled`, `Source_Dataset`, `Source_FeatureClass`,
`Target_Dataset`, `Target_FeatureClass`, `Rule`, `Filter`, and `Geometry_Rule`.

| Column | Meaning |
| --- | --- |
| Source_Dataset / Target_Dataset | Optional feature dataset names. |
| Source_FeatureClass / Target_FeatureClass | Source and existing template target FC names. |
| Rule | `COPY`, `SPLIT`, `MERGE`, `IGNORE`, or `EMPTY`. |
| Filter | Optional source SQL where clause. |
| Geometry_Rule | `KEEP`, `SINGLEPART`, `CENTROID`, `BOUNDARY`, `BUFFER`, or `PROJECT`. |

```csv
Enabled,Source_Dataset,Source_FeatureClass,Target_Dataset,Target_FeatureClass,Rule,Filter,Geometry_Rule
Yes,Transportation,Road,Transportation,Road,COPY,,KEEP
Yes,Utility,Pole,Utility,ElectricPole,SPLIT,TYPE='ELEC',KEEP
```

`COPY`, `SPLIT`, and `MERGE` migrate rows. `IGNORE` skips source rows and
`EMPTY` leaves the copied template target empty. Version 1.0 executes only
`KEEP` geometry transfer; other geometry rules are validated but not executed.

## Field_Mapping.csv

Required columns: `Enabled`, `Source_FeatureClass`, `Source_Field`,
`Target_FeatureClass`, `Target_Field`, `Rule`, `Parameter`, and `Default_Value`.
The target field must already exist in the template.

| Rule | Result |
| --- | --- |
| COPY | Writes the source-field value. |
| DOMAIN | Maps through the named domain mapping in `Parameter`. |
| DEFAULT | Writes `Default_Value`. |
| UUID | Writes a generated UUID. |
| LOOKUP | Maps through the named lookup in `Parameter`. |
| EXPRESSION / CALCULATE | Evaluates a safe expression; use `!FIELD!` tokens. |
| CONCAT | Joins values named in `Parameter`. |
| SPLIT / SUBSTRING / DATEFORMAT | Applies the documented string/date operation in `Parameter`. |
| IGNORE | Does not assign the target field. |

```csv
Enabled,Source_FeatureClass,Source_Field,Target_FeatureClass,Target_Field,Rule,Parameter,Default_Value
Yes,Road,ROAD_NAME,Road,Name,COPY,,
Yes,Road,ROAD_TYPE,Road,Type,DOMAIN,RoadType,
Yes,Road,,Road,Status,DEFAULT,,Active
Yes,Road,,Road,TopoID,UUID,,
Yes,Building,FLOORS,Building,Height,EXPRESSION,!FLOORS!*3,
```

`DEFAULT`, `UUID`, and `IGNORE` can use a blank `Source_Field`; other rules
normally require one.

## Domain_Mapping.csv

Required columns: `Enabled`, `Source_FeatureClass`, `Source_Field`,
`Source_Code`, `Target_FeatureClass`, `Target_Field`, `Target_Code`, and
`Description`. Each row maps a source code to a code already in the domain
assigned to the target field. GMF never creates or changes domains.

## Lookup.csv

Use either a value-map with `Lookup_Name`, `Source_Value`, `Target_Value`, and
optional `Description`; or the AMRUT definition manifest with `Column`,
`Required`, and `Description`. The manifest validates a proposed schema but
does not provide values for a `LOOKUP` transform; use the value-map format for
actual lookup mapping.
