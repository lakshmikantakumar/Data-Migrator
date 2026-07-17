"""Unit tests for typed GMF CSV rule loading."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from toolbox import rules
from toolbox.utils.exception_utils import ConfigurationError


class RulesTests(unittest.TestCase):
    """Verify supplied configuration parsing and mandatory-file behavior."""

    def test_loads_amrut_configuration_as_immutable_typed_rules(self) -> None:
        """All supplied configuration rows become typed immutable objects."""
        rule_set = rules.load_configuration("configs/AMRUT")
        self.assertEqual((len(rule_set.feature_class_rules), len(rule_set.field_rules), len(rule_set.domain_rules)), (4, 5, 4))
        self.assertTrue(all(isinstance(item, rules.FeatureClassRule) for item in rule_set.feature_class_rules))
        self.assertTrue(all(isinstance(item, rules.FieldRule) for item in rule_set.field_rules))
        self.assertTrue(all(isinstance(item, rules.DomainRule) for item in rule_set.domain_rules))
        self.assertTrue(all(isinstance(item, rules.LookupColumnRule) for item in rule_set.lookup_rules))
        self.assertEqual(rule_set.feature_class_rules[0].geometry_rule, rules.GeometryRuleName.KEEP)
        with self.assertRaises(FrozenInstanceError):
            rule_set.field_rules[0].target_field = "Other"

    def test_missing_mandatory_mapping_file_raises_configuration_error(self) -> None:
        """Load fails clearly when required configuration files are absent."""
        temporary_folder = Path(__file__).parent / "_test_output" / self._testMethodName
        temporary_folder.mkdir(parents=True, exist_ok=True)
        try:
            with self.assertRaises(ConfigurationError):
                rules.load_configuration(str(temporary_folder))
        finally:
            temporary_folder.rmdir()


if __name__ == "__main__":
    unittest.main()
