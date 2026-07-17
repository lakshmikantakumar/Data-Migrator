"""Unit tests for GMF validation and Validation_Report.csv output."""

from __future__ import annotations

import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from toolbox import validator
from toolbox.utils.gdb_utils import FeatureClassInfo


class ValidatorTests(unittest.TestCase):
    """Verify validation checks are accumulated and reported as CSV."""

    def test_validates_configuration_and_writes_report(self) -> None:
        """Mocked GDB metadata produces a successful typed validation report."""
        @contextmanager
        def search_cursor(*args: object, **kwargs: object):
            yield iter(())

        description = SimpleNamespace(shapeType="Polyline")
        feature_info = FeatureClassInfo("feature", "feature", "Polyline", "WGS 1984", 4326, {})
        fields = {"Name": {"domain": "RoadType"}, "Type": {"domain": "RoadType"}, "Status": {"domain": ""}, "TopoID": {"domain": ""}, "Height": {"domain": ""}}
        domains = {"RoadType": {"coded_values": {"NH": "National Highway", "SH": "State Highway", "Agriculture": "Agriculture", "Forest": "Forest"}}}

        report_folder = Path(__file__).parent / "_test_output" / self._testMethodName
        report_folder.mkdir(parents=True, exist_ok=True)
        try:
            with (
                patch.object(validator.gdb_utils, "validate_geodatabase"),
                patch.object(validator.gdb_utils, "validate_feature_class", return_value=description),
                patch.object(validator.gdb_utils, "feature_class_information", return_value=feature_info),
                patch.object(validator.gdb_utils, "field_exists", return_value=True),
                patch.object(validator.gdb_utils, "field_information", return_value=fields),
                patch.object(validator.gdb_utils, "domain_information", return_value=domains),
                patch.object(validator, "search_cursor", search_cursor),
            ):
                summary = validator.Validator("configs/AMRUT", "source.gdb", "template.gdb", str(report_folder)).validate()

            report_path = Path(summary.report_path)
            self.assertTrue(summary.passed)
            self.assertTrue(report_path.is_file())
            self.assertIn("Configuration,PASS", report_path.read_text(encoding="utf-8-sig"))
        finally:
            report_path = report_folder / "Validation_Report.csv"
            if report_path.exists():
                report_path.unlink()
            report_folder.rmdir()


if __name__ == "__main__":
    unittest.main()
