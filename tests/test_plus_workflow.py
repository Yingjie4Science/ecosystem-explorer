"""Fast contract tests; no app import and no supplied PLUS binary required."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

import plus_workflow as w
from scripts.run_canonical_plus_bundle import extract_checked
from scripts.compare_plus_canonical import carbon_density_to_co2


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.current = np.array([[1, 11], [12, -1]], dtype=np.int16)
        self.future = np.array([[1, 4], [12, -1]], dtype=np.int16)
        self.restricted = np.array([[True, False], [False, True]])
        self.allowed = [(11, 4)]

    def test_valid_native(self):
        self.assertEqual(w.validate_native(self.current, self.future, self.restricted, self.allowed)["changed_cells"], 1)

    def test_unknown_class_rejected(self):
        arr = self.future.copy(); arr[0, 1] = 99
        with self.assertRaisesRegex(ValueError, "Unknown"):
            w.validate_native(self.current, arr, self.restricted, self.allowed)

    def test_nodata_drift_rejected(self):
        arr = self.future.copy(); arr[1, 1] = 4
        with self.assertRaisesRegex(ValueError, "Nodata"):
            w.validate_native(self.current, arr, self.restricted, self.allowed)

    def test_restricted_rejected(self):
        arr = self.future.copy(); arr[0, 0] = 4
        with self.assertRaisesRegex(ValueError, "restricted"):
            w.validate_native(self.current, arr, self.restricted, self.allowed)

    def test_transition_rejected(self):
        with self.assertRaisesRegex(ValueError, "Prohibited"):
            w.validate_native(self.current, self.future, self.restricted, [])

    def test_unchanged_compound_preserved(self):
        base = np.array([[14, 54], [93, -1]])
        result = w.expand_compound(self.current, self.future, base, {4: 341})
        np.testing.assert_array_equal(result, [[14, 341], [93, -1]])

    def test_missing_crosswalk_rejected(self):
        with self.assertRaisesRegex(ValueError, "crosswalk"):
            w.expand_compound(self.current, self.future, self.current, {})

    def test_native_demand_contract_and_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            demand = out / "demand.csv"
            w.write_csv(demand, [{"planning_class": c, "target_cells": 1} for c in (1, 4, 12)], ["planning_class", "target_cells"])
            profile = dict(driver="GTiff", height=2, width=2, count=1, dtype="int16", crs="EPSG:5070", transform=from_origin(0, 60, 30, 30))
            rows = [{"planning_class": 4, "representative_compound_lucode": 341}]
            result, qc = w.package_native(out, self.current, self.current, self.future, self.restricted,
                self.allowed, rows, profile, {"name": "PLUS", "demand_path": str(demand)})
            self.assertTrue(qc["demand_counts_match"])
            self.assertEqual(result[0, 1], 341)
            self.assertTrue((out / "canonical/transition_counts.csv").is_file())
            w.write_csv(demand, [{"planning_class": 4, "target_cells": 5}], ["planning_class", "target_cells"])
            with self.assertRaisesRegex(ValueError, "demand counts"):
                w.package_native(out, self.current, self.current, self.future, self.restricted,
                    self.allowed, rows, profile, {"name": "PLUS", "demand_path": str(demand)})

    def test_hindcast_and_persistence(self):
        perfect = w.hindcast_metrics(self.current, self.future, self.future)
        self.assertEqual(perfect["figure_of_merit"], 1)
        self.assertEqual(perfect["total_disagreement"], 0)
        persistence = w.hindcast_metrics(self.current, self.future, self.current)
        self.assertEqual(persistence["figure_of_merit"], 0)
        self.assertAlmostEqual(persistence["quantity_disagreement"], 1 / 3)

    def test_hindcast_no_change_not_perfect_claim(self):
        self.assertIsNone(w.hindcast_metrics(self.current, self.current, self.current)["figure_of_merit"])

    def test_hindcast_wrong_destination_not_hit(self):
        arr = self.future.copy(); arr[0, 1] = 5
        self.assertEqual(w.hindcast_metrics(self.current, self.future, arr)["figure_of_merit"], 0)

    def test_area_and_nodata_counts(self):
        rows = w.transition_rows(self.current, self.future, 900)
        self.assertEqual(sum(r["cells"] for r in rows), 3)
        self.assertAlmostEqual(sum(r["area_ha"] for r in rows), .27)

    def test_fixture_reproducible_and_exact_quantity(self):
        arr = np.full((20, 20), 12, dtype=np.int16); arr[:, :3] = 4
        a, b = w.fixture_future(arr, 20, 42), w.fixture_future(arr, 20, 42)
        np.testing.assert_array_equal(a, b)
        self.assertEqual(np.count_nonzero(a != arr), 20)

    def test_fixture_invalid_quantity(self):
        with self.assertRaises(ValueError):
            w.fixture_future(self.current, 0, 42)

    def test_canonical_bundle_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../escaped.txt", "unsafe")
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                extract_checked(path, Path(tmp) / "output")

    def test_carbon_density_is_integrated_over_cell_area(self):
        self.assertAlmostEqual(carbon_density_to_co2([100, -50], .09), 16.5)

    def test_food_quarter_acre_units_and_discount(self):
        record = json.loads((w.ROOT / "data/sa/food_forest_yield_report_2023.json").read_text())
        total, rows = w.food_yield_capacity(1, 4046.8564224, record)
        self.assertEqual(total, 11438)
        self.assertEqual(len(rows), 4)
        self.assertEqual(w.food_yield_capacity(1, 4046.8564224, record, .5)[0], 5719)
        with self.assertRaises(ValueError):
            w.food_yield_capacity(1, 900, record, 2)

    def test_random_comparator_quantity_and_restrictions(self):
        current = np.full((10, 10), 12, dtype=np.int16)
        obs = current.copy(); obs[:2, :] = 4
        restricted = np.zeros(current.shape, bool); restricted[5:, :] = True
        result = w.quantity_correct_random(current, obs, 42, restricted)
        self.assertEqual(int((result == 4).sum()), 20)
        self.assertFalse(np.any((current != result) & restricted))
        np.testing.assert_array_equal(result, w.quantity_correct_random(current, obs, 42, restricted))

    def test_integrity_modified_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.txt"; path.write_text("original")
            w.write_json(Path(tmp) / "manifest.json", {"production_release_allowed": False,
                "artifacts_sha256": {"artifact.txt": w.sha256(path)}})
            self.assertTrue(w.verify_run(tmp)["passed"])
            path.write_text("changed")
            with self.assertRaisesRegex(ValueError, "modified"):
                w.verify_run(tmp)

    def test_engine_record_cannot_use_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "record.json"
            path.write_text(json.dumps({"name": "PLUS", "version": "REQUIRED"}))
            with self.assertRaises(ValueError):
                w.load_engine_record(path)

    def test_raster_crs_and_transform_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lulc.tif"
            profile = dict(driver="GTiff", height=2, width=2, count=1, dtype="int16", crs="EPSG:5070", transform=from_origin(0, 60, 30, 30))
            w.write_raster(path, self.current, profile)
            _, ref = w.read_raster(path)
            ref["transform"] = from_origin(30, 60, 30, 30)
            with self.assertRaisesRegex(ValueError, "grid mismatch"):
                w.read_raster(path, reference=ref)
            with self.assertRaisesRegex(ValueError, "CRS"):
                w.read_raster(path, expected_crs="EPSG:3857")


if __name__ == "__main__":
    unittest.main()
