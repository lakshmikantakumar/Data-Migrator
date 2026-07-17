"""Unit tests for all typed field transformation classes."""

from __future__ import annotations

import unittest

from toolbox.rules import FieldRule, FieldRuleName
from toolbox.transform import TransformContext, TransformEngine


def _rule(name: str, source_field: str | None = "A", parameter: str | None = None, default_value: str | None = None) -> FieldRule:
    """Create a compact typed rule for one transformer test."""
    return FieldRule(True, "Source", source_field, "Target", "Output", FieldRuleName(name), parameter, default_value, 2)


class TransformTests(unittest.TestCase):
    """Verify all requested transformation rules through TransformEngine."""

    def setUp(self) -> None:
        """Create a source row and reusable mapping tables."""
        self.context = TransformContext(
            source_row={"A": "one,two,three", "B": "beta", "NUM": 5, "DATE": "2026-07-16", "CODE": "1"},
            domain_mappings={"RoadType": {"1": "NH"}},
            lookup_tables={"Names": {"1": "National Highway"}},
            concat_separator="|",
        )
        self.engine = TransformEngine()

    def test_all_field_rules(self) -> None:
        """COPY through IGNORE produce the documented transform outcomes."""
        cases = (
            (_rule("COPY"), "one,two,three"),
            (_rule("DOMAIN", "CODE", "RoadType"), "NH"),
            (_rule("DEFAULT", None, default_value="Active"), "Active"),
            (_rule("LOOKUP", "CODE", "Names"), "National Highway"),
            (_rule("EXPRESSION", "NUM", "!NUM! * 3"), 15),
            (_rule("CONCAT", "A", "A,B"), "one,two,three|beta"),
            (_rule("SPLIT", "A", ",|1"), "two"),
            (_rule("SUBSTRING", "B", "1,2"), "et"),
            (_rule("DATEFORMAT", "DATE", "%Y-%m-%d|%d/%m/%Y"), "16/07/2026"),
            (_rule("CALCULATE", "NUM", "value + 7"), 12),
        )
        for rule, expected in cases:
            with self.subTest(rule=rule.rule.value):
                self.assertEqual(self.engine.transform(rule, self.context).value, expected)
        uuid_result = self.engine.transform(_rule("UUID", None), self.context)
        self.assertTrue(uuid_result.assign and uuid_result.value.startswith("{"))
        self.assertFalse(self.engine.transform(_rule("IGNORE", None), self.context).assign)


if __name__ == "__main__":
    unittest.main()
