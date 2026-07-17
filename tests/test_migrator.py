"""Unit tests for cursor-only COPY, SPLIT, and MERGE migration."""

from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from toolbox import migrator
from toolbox.rules import FeatureClassRule, FeatureClassRuleName, FieldRule, FieldRuleName, GeometryRuleName, RuleSet


class _Logger:
    """Minimal Logger-compatible recorder for migration tests."""

    def __init__(self) -> None:
        self.errors = []

    def section(self, *args: object) -> None: pass
    def info(self, *args: object) -> None: pass
    def statistics(self, *args: object) -> None: pass
    def close(self) -> None: pass
    def error(self, message: str) -> None: self.errors.append(message)


class _Progress:
    """Minimal ProgressManager replacement independent of ArcPy."""

    def __init__(self, *args: object) -> None: self.updates = []
    def start(self) -> None: pass
    def update(self, label: str | None = None) -> None: self.updates.append(label)
    def finish(self) -> None: pass


class MigratorTests(unittest.TestCase):
    """Verify streaming inserts and aggregate statistics for core FC rules."""

    def test_copy_split_and_merge_use_source_and_insert_cursors(self) -> None:
        """Each configured source is read once and inserted into its target."""
        def feature_rule(source: str, target: str, name: str, where: str | None = None) -> FeatureClassRule:
            return FeatureClassRule(True, None, source, None, target, FeatureClassRuleName(name), where, GeometryRuleName.KEEP, 2)

        def field_rule(source: str, target: str) -> FieldRule:
            return FieldRule(True, source, "NAME", target, "Name", FieldRuleName.COPY, None, None, 2)

        rule_set = RuleSet(
            (
                feature_rule("Road", "RoadOut", "COPY"),
                feature_rule("Pole", "ElectricPole", "SPLIT", "TYPE='ELEC'"),
                feature_rule("River", "Water", "MERGE"),
                feature_rule("Canal", "Water", "MERGE"),
            ),
            (field_rule("Road", "RoadOut"), field_rule("Pole", "ElectricPole"), field_rule("River", "Water"), field_rule("Canal", "Water")),
            (), (),
        )
        source_rows = {
            os.path.join("source.gdb", "Road"): [("road-shape", "Road")],
            os.path.join("source.gdb", "Pole"): [("pole-shape", "Pole")],
            os.path.join("source.gdb", "River"): [("river-shape", "River")],
            os.path.join("source.gdb", "Canal"): [("canal-shape", "Canal")],
        }
        inserted = {}

        @contextmanager
        def search_cursor(path: str, fields: object, where_clause: str | None = None):
            yield iter(source_rows[path])

        @contextmanager
        def insert_cursor(path: str, fields: object):
            class Cursor:
                def insertRow(self, row: object) -> None:
                    inserted.setdefault(path, []).append(row)
            yield Cursor()

        with (
            patch.object(migrator.gdb_utils, "validate_geodatabase"),
            patch.object(migrator.gdb_utils, "validate_feature_class"),
            patch.object(migrator.arcpy_utils, "search_cursor", search_cursor),
            patch.object(migrator.arcpy_utils, "insert_cursor", insert_cursor),
            patch.object(migrator, "ProgressManager", _Progress),
        ):
            summary = migrator.Migrator(
                "source.gdb", "target.gdb", rule_set, _Logger(),
                options=migrator.MigrationOptions(validate_field_schema=False),
            ).migrate()

        self.assertTrue(summary.success)
        self.assertEqual((summary.features_read, summary.features_migrated, summary.features_failed), (4, 4, 0))
        self.assertEqual(len(inserted[os.path.join("target.gdb", "Water")]), 2)


if __name__ == "__main__":
    unittest.main()
