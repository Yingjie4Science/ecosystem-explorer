"""Manufactured landscape and file-contract tests; not native PLUS parity."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import rasterio
from rasterio.transform import from_origin

from plus_inspired import core, model
from plus_inspired.runner import execute, verify


class ArrayContracts(unittest.TestCase):
    def setUp(self):
        self.initial = np.ones((8, 8), dtype=np.int16)
        self.initial[0] = 2
        self.valid = np.ones((8, 8), dtype=bool)
        self.prob = np.ones((2, 8, 8), dtype=np.float32)
        self.edit = self.valid.copy()

    def allocate(self, **kwargs):
        values = dict(initial=self.initial, probabilities=self.prob, valid=self.valid,
                      editable=self.edit, classes=[1, 2], demand=[32, 32], transitions=[[1, 1], [0, 1]])
        values.update(kwargs)
        return core.allocate(**values)

    def test_exact_and_repeatable(self):
        a, details = self.allocate(batch_size=4)
        b, _ = self.allocate(batch_size=4)
        np.testing.assert_array_equal(a, b)
        self.assertEqual(details["final_counts"], [32, 32])
        self.assertEqual(details["changed_cells"], 24)

    def test_persistence(self):
        result, _ = self.allocate(demand=[56, 8], probabilities=self.prob * 0)
        np.testing.assert_array_equal(result, self.initial)

    def test_locked_infeasible(self):
        with self.assertRaisesRegex(ValueError, "infeasible"):
            self.allocate(editable=self.edit * False)

    def test_locked_preserved(self):
        self.edit[:, :2] = False
        result, _ = self.allocate()
        np.testing.assert_array_equal(result[~self.edit], self.initial[~self.edit])

    def test_zero_suitability(self):
        with self.assertRaisesRegex(ValueError, "infeasible"):
            self.allocate(probabilities=self.prob * 0)

    def test_forbidden_transition(self):
        with self.assertRaisesRegex(ValueError, "infeasible"):
            self.allocate(transitions=[[1, 0], [0, 1]])

    def test_partial_capacity(self):
        self.edit[2:] = False
        with self.assertRaisesRegex(ValueError, "infeasible"):
            self.allocate()

    def test_incomplete_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.allocate(batch_size=1, max_rounds=1)

    def test_unknown_class(self):
        self.initial[1, 1] = 99
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.allocate()

    def test_invalid_probability(self):
        self.prob[0, 1, 1] = np.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            self.allocate()

    def test_fractional_demand(self):
        with self.assertRaisesRegex(ValueError, "integer"):
            self.allocate(demand=[31.5, 32.5])

    def test_nodata_preserved(self):
        self.valid[-1] = False
        self.edit[-1] = False
        self.initial[-1] = -1
        result, _ = self.allocate(demand=[28, 28])
        np.testing.assert_array_equal(result[-1], self.initial[-1])

    def test_class_permutation(self):
        # Flow ties may differ with schema order; invariants must not.
        result, details = self.allocate(classes=[2, 1], demand=[32, 32], transitions=[[1, 0], [1, 1]])
        self.assertEqual(details["changed_cells"], 24)
        self.assertEqual(int((result == 2).sum()), 32)

    def test_competing_groups_capacity(self):
        initial = np.ones((4, 4), dtype=np.int16)
        prob = np.ones((3, 4, 4), dtype=np.float32)
        prob[2, :2] = 0
        result, _ = core.allocate(initial, prob, np.ones((4, 4), bool), np.ones((4, 4), bool),
                                  [1, 2, 3], [0, 8, 8], np.ones((3, 3), int), batch_size=2)
        self.assertTrue((result[:2] == 2).all())
        self.assertTrue((result[2:] == 3).all())

    def test_invalid_parameters(self):
        for kwargs in [dict(seed=-1), dict(neighborhood=2), dict(patch_weight=-1), dict(batch_size=0)]:
            with self.assertRaises(ValueError):
                self.allocate(**kwargs)

    def test_zero_class_expansion(self):
        end = self.initial.copy()
        end[1] = 0
        result = core.expansion(self.initial, end, self.valid, [0, 1, 2])
        self.assertTrue((result[1] == 0).all())
        self.assertTrue((result[0] == -2).all())

    def test_validator(self):
        changed, _ = self.allocate()
        perfect = core.validate(self.initial, changed, changed, self.valid, [1, 2])
        self.assertEqual(perfect["figure_of_merit"], 1)
        self.assertEqual(perfect["allocation_disagreement"], 0)
        persistence = core.validate(self.initial, changed, self.initial, self.valid, [1, 2])
        self.assertEqual(persistence["figure_of_merit"], 0)
        same = core.validate(self.initial, self.initial, self.initial, self.valid, [1, 2])
        self.assertIsNone(same["figure_of_merit"])

    def test_json_forest_repeatable_and_safe(self):
        end = self.initial.copy()
        end[3:5] = 2
        drivers = np.indices(self.initial.shape).astype(np.float32)
        fitted = model.fit(self.initial, end, drivers, self.valid, [1, 2], trees=4)
        roundtrip = json.loads(json.dumps(fitted))
        probabilities = model.predict(roundtrip, drivers, self.valid)
        repeated = model.predict(model.fit(self.initial, end, drivers, self.valid, [1, 2], trees=4), drivers, self.valid)
        np.testing.assert_array_equal(probabilities, repeated)
        self.assertTrue((probabilities[0] == 0).all())
        damaged = copy.deepcopy(roundtrip)
        damaged["models"][1]["trees"][0]["left"][0] = 0
        with self.assertRaisesRegex(ValueError, "cyclic"):
            model.predict(damaged, drivers, self.valid)

    def test_serialization_matches_sklearn(self):
        from sklearn.ensemble import RandomForestClassifier
        end = self.initial.copy()
        end[3:5] = 2
        drivers = np.indices(self.initial.shape).astype(np.float32)
        fitted = model.fit(self.initial, end, drivers, self.valid, [1, 2], trees=4)
        selected = np.random.default_rng(42).choice(np.arange(64), 64, replace=False)
        x = drivers.reshape(2, -1).T
        y = (core.expansion(self.initial, end, self.valid, [1, 2]).ravel() == 2).astype(np.uint8)
        reference = RandomForestClassifier(n_estimators=4, max_depth=12, min_samples_leaf=2,
                                           max_features="sqrt", random_state=43, n_jobs=1).fit(x[selected], y[selected])
        np.testing.assert_allclose(model.predict(fitted, drivers, self.valid)[1].ravel(),
                                   reference.predict_proba(x)[:, 1], atol=1e-7)

    def test_net_change_scope_rejects_indirect_exchange(self):
        initial = np.array([[1, 1], [2, 2]], np.int16)
        with self.assertRaisesRegex(ValueError, "infeasible"):
            core.allocate(initial, np.ones((3, 2, 2)), np.ones((2, 2), bool), np.ones((2, 2), bool),
                          [1, 2, 3], [1, 2, 1], [[1, 1, 0], [0, 1, 1], [0, 0, 1]])


class FileContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.profile = dict(driver="GTiff", height=8, width=8, count=1, dtype="int16",
                            crs="EPSG:5070", transform=from_origin(0, 240, 30, 30), nodata=-1)
        initial = np.ones((8, 8), dtype=np.int16)
        initial[0] = 2
        end = initial.copy()
        end[3:5, :4] = 2
        for name, values in [("initial", initial), ("end", end), ("driver", np.indices((8, 8))[0]), ("edit", np.ones((8, 8)))]:
            with rasterio.open(self.root / f"{name}.tif", "w", **self.profile) as dst:
                dst.write(values.astype(np.int16), 1)
        self.config = dict(format="plus-inspired-config-v1", command="fit", classes=[1, 2], crs="EPSG:5070",
                           initial="initial.tif", end="end.tif", origin_year=2005, end_year=2015,
                           dataset_collection="synthetic-v1", trees=4,
                           drivers=[dict(name="row", path="driver.tif", year=2005, kind="continuous")])

    def tearDown(self):
        self.temporary.cleanup()

    def run_config(self, command, config, name):
        path = self.root / f"{name}.json"
        path.write_text(json.dumps(config))
        return execute(command, path, self.root / name)

    def test_full_file_chain(self):
        receipt = self.run_config("fit", self.config, "fit")
        self.assertFalse(receipt["production_release"])
        prediction = {k: self.config[k] for k in ["format", "classes", "crs", "dataset_collection", "drivers"]}
        prediction.update(command="predict", initial="end.tif", origin_year=2015, model="fit/model.json")
        self.run_config("predict", prediction, "prediction")
        allocation = {k: prediction[k] for k in ["format", "classes", "crs", "initial", "origin_year", "dataset_collection"]}
        allocation.update(command="allocate", target_year=2050, editable="edit.tif", demand={"1": 40, "2": 24},
                          probabilities={str(c): f"prediction/probability_{c}.tif" for c in [1, 2]}, transitions=[[1, 1], [0, 1]])
        self.run_config("allocate", allocation, "allocation")
        validation = {k: allocation[k] for k in ["format", "classes", "crs", "initial"]}
        validation.update(command="validate", observed="allocation/land_cover.tif", simulated="allocation/land_cover.tif")
        self.run_config("validate", validation, "validation")
        result = json.loads((self.root / "validation/validation.json").read_text())
        self.assertEqual(result["figure_of_merit"], 1)

    def test_future_driver_rejected_with_receipt(self):
        self.config["drivers"][0]["year"] = 2025
        with self.assertRaisesRegex(ValueError, "leaks"):
            self.run_config("fit", self.config, "failed")
        receipt = json.loads((self.root / "failed/receipt.json").read_text())
        self.assertEqual(receipt["status"], "rejected")
        self.assertFalse((self.root / "failed/model.json").exists())

    def test_artifact_tampering(self):
        self.run_config("fit", self.config, "fit")
        result = verify(self.root / "fit", check_inputs=True)
        self.assertEqual(result["verified_artifacts"], 2)
        (self.root / "fit/model.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "integrity"):
            verify(self.root / "fit")

    def test_truth_rejected(self):
        self.config["truth"] = "end.tif"
        with self.assertRaisesRegex(ValueError, "unknown config"):
            self.run_config("fit", self.config, "failed")

    def test_overwrite_refused(self):
        self.run_config("fit", self.config, "fit")
        with self.assertRaises(FileExistsError):
            self.run_config("fit", self.config, "fit")

    def test_grid_drift(self):
        profile = self.profile.copy()
        profile["transform"] = from_origin(1, 240, 30, 30)
        with rasterio.open(self.root / "end.tif", "w", **profile) as dst:
            dst.write(np.ones((8, 8), np.int16), 1)
        with self.assertRaisesRegex(ValueError, "grid mismatch"):
            self.run_config("fit", self.config, "failed")

    def test_missing_support(self):
        array = np.ones((8, 8), np.int16)
        array[1, 1] = -1
        with rasterio.open(self.root / "driver.tif", "w", **self.profile) as dst:
            dst.write(array, 1)
        with self.assertRaisesRegex(ValueError, "missing"):
            self.run_config("fit", self.config, "failed")

    def test_web_mercator_rejected(self):
        self.config["crs"] = "EPSG:3857"
        with self.assertRaisesRegex(ValueError, "Mercator"):
            self.run_config("fit", self.config, "failed")


if __name__ == "__main__":
    unittest.main()
