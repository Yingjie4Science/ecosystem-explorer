"""Strict raster/config IO and receipts for the offline experimental engine."""
from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import version
import hashlib
import json
from pathlib import Path
import platform
import subprocess

import numpy as np
import rasterio

from . import ENGINE, VERSION
from . import core, model


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path):
    if Path(path).stat().st_size > 64 * 1024 * 1024:
        raise ValueError("JSON input exceeds 64 MiB bound")
    with Path(path).open() as source:
        return json.load(source)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def grid_equal(a, b):
    return all(a[key] == b[key] for key in ["crs", "transform", "width", "height"])


def read(path, crs, reference=None, categorical=False):
    with rasterio.open(path) as source:
        if source.crs != rasterio.crs.CRS.from_user_input(crs):
            raise ValueError(f"{path}: CRS mismatch")
        profile = source.profile.copy()
        if source.count != 1 or (reference is not None and not grid_equal(profile, reference)):
            raise ValueError(f"{path}: band/grid mismatch; prepare alignment explicitly")
        data = source.read(1)
        valid = source.read_masks(1) > 0
        valid &= np.isfinite(data)
        if categorical and not np.issubdtype(data.dtype, np.integer):
            raise ValueError(f"{path}: categorical values must be integers")
    return data, valid, profile


def write_raster(path, values, profile, nodata=-1):
    profile = profile.copy()
    dtype = "int16" if np.issubdtype(values.dtype, np.integer) else "float32"
    profile.update(driver="GTiff", count=1, dtype=dtype, nodata=nodata, compress="deflate")
    with rasterio.open(path, "w", **profile) as target:
        if target.crs != profile["crs"]:
            raise ValueError("output CRS mismatch")
        target.write(values.astype(dtype), 1)


def execute(command, config_path, output):
    config_path = Path(config_path).resolve()
    config = load_json(config_path)
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=False)
    inputs = {str(config_path): digest(config_path)}

    def path(key):
        p = Path(key)
        p = (config_path.parent / p).resolve() if not p.is_absolute() else p.resolve()
        inputs[str(p)] = digest(p)
        return p

    receipt = {"engine": ENGINE, "version": VERSION, "command": command,
               "production_release": False, "native_plus_equivalence": "not_established",
               "timestamp_utc": datetime.now(timezone.utc).isoformat(), "config": config,
               "inputs_sha256": inputs, "platform": platform.platform(),
               "dependencies": {p: version(p) for p in ["numpy", "scipy", "rasterio", "scikit-learn"]},
               "source_sha256": {p.name: digest(p) for p in Path(__file__).parent.glob("*.py")}}
    try:
        if config.get("format") != "plus-inspired-config-v1":
            raise ValueError("unsupported config format")
        if config.get("command") != command:
            raise ValueError("config command mismatch")
        permitted = {"format", "command", "classes", "crs", "initial", "origin_year", "dataset_collection"}
        permitted |= {"fit": {"end", "end_year", "drivers", "seed", "trees", "max_samples"},
                      "predict": {"model", "drivers"},
                      "allocate": {"probabilities", "editable", "target_year", "demand", "transitions", "seed", "neighborhood", "patch_weight", "stochasticity", "batch_size", "max_rounds"},
                      "validate": {"observed", "simulated"}}[command]
        if set(config) - permitted:
            raise ValueError(f"unknown config fields: {sorted(set(config) - permitted)}")
        classes = core.schema(config["classes"])
        crs = config["crs"]
        parsed_crs = rasterio.crs.CRS.from_user_input(crs)
        if not parsed_crs.is_projected or parsed_crs.to_epsg() == 3857 or parsed_crs.linear_units != "metre":
            raise ValueError("meter-based projected analysis CRS required; Web Mercator forbidden")
        initial, valid, profile = read(path(config["initial"]), crs, categorical=True)
        core.categorical(initial, valid, classes)

        def epoch(key):
            array, support, _ = read(path(config[key]), crs, profile, categorical=True)
            if not np.array_equal(support, valid):
                raise ValueError("epoch validity support mismatch")
            core.categorical(array, valid, classes)
            return array

        def features():
            drivers = config["drivers"]
            if not drivers or len({d["name"] for d in drivers}) != len(drivers):
                raise ValueError("driver names must be unique and nonempty")
            arrays = []
            for driver in drivers:
                if set(driver) != {"name", "path", "year", "kind"} or driver["kind"] != "continuous":
                    raise ValueError("v1 drivers require name/path/year/kind=continuous")
                if type(driver["year"]) is not int or driver["year"] > config["origin_year"]:
                    raise ValueError("driver date leaks past prediction/training origin")
                array, support, _ = read(path(driver["path"]), crs, profile)
                if not support[valid].all():
                    raise ValueError("driver missing on valid support")
                arrays.append(array.astype(np.float32))
            return np.stack(arrays)

        if command in ["fit", "predict", "allocate"] and (type(config.get("origin_year")) is not int or not config.get("dataset_collection")):
            raise ValueError("origin_year and dataset_collection provenance required")
        if command == "fit":
            if type(config["end_year"]) is not int or config["end_year"] <= config["origin_year"]:
                raise ValueError("training end must follow origin")
            end = epoch("end")
            fitted = model.fit(initial, end, features(), valid, classes,
                               **{k: config[k] for k in ["seed", "trees", "max_samples"] if k in config})
            fitted.update(training_start=config["origin_year"], training_end=config["end_year"],
                          dataset_collection=config["dataset_collection"],
                          feature_names=[d["name"] for d in config["drivers"]], training_inputs_sha256=inputs.copy())
            write_json(output / "model.json", fitted)
            write_raster(output / "expansion.tif", core.expansion(initial, end, valid, classes), profile)
        elif command == "predict":
            fitted = load_json(path(config["model"]))
            if fitted["classes"] != list(classes) or fitted["feature_names"] != [d["name"] for d in config["drivers"]] or fitted["dataset_collection"] != config["dataset_collection"] or fitted["training_end"] > config["origin_year"]:
                raise ValueError("model classes/features/collection/origin mismatch")
            drivers = features()
            probabilities = model.predict(fitted, drivers, valid)
            receipt["out_of_training_range_cells"] = {
                d["name"]: int((valid & ((array < limits[0]) | (array > limits[1]))).sum())
                for d, array, limits in zip(config["drivers"], drivers, fitted["feature_ranges"])}
            for code, array in zip(classes, probabilities):
                write_raster(output / f"probability_{code}.tif", np.where(valid, array, -1), profile)
        elif command == "allocate":
            if type(config["target_year"]) is not int or config["target_year"] <= config["origin_year"]:
                raise ValueError("target year must follow origin")
            if set(config["probabilities"]) != {str(c) for c in classes} or set(config["demand"]) != {str(c) for c in classes}:
                raise ValueError("explicit probability and demand entries required for every class")
            if any(type(value) is not int for value in config["demand"].values()):
                raise ValueError("demand values must be JSON integers, not booleans/fractions")
            layers = []
            for code in classes:
                array, support, _ = read(path(config["probabilities"][str(code)]), crs, profile)
                if not support[valid].all():
                    raise ValueError("probability missing on valid support")
                layers.append(array)
            editable, support, _ = read(path(config["editable"]), crs, profile, categorical=True)
            if not support[valid].all() or not np.isin(editable[valid], [0, 1]).all():
                raise ValueError("editable raster must be complete binary on valid support")
            result, diagnostics = core.allocate(initial, np.stack(layers), valid, valid & (editable == 1), classes,
                                                 [config["demand"][str(c)] for c in classes], config["transitions"],
                                                 **{k: config[k] for k in ["seed", "neighborhood", "patch_weight", "stochasticity", "batch_size", "max_rounds"] if k in config})
            receipt["diagnostics"] = diagnostics
            write_raster(output / "land_cover.tif", np.where(valid, result, -1), profile)
        elif command == "validate":
            observed, simulated = epoch("observed"), epoch("simulated")
            report = core.validate(initial, observed, simulated, valid, classes)
            report["persistence_baseline"] = core.validate(initial, observed, initial, valid, classes)
            report["validation_scope"] = "input-matched comparison; independence and decision fitness require review"
            write_json(output / "validation.json", report)
        receipt["status"] = "completed_experimental"
    except Exception as error:
        receipt["status"] = "rejected"
        receipt["error"] = f"{type(error).__name__}: {error}"
        write_json(output / "receipt.json", receipt)
        raise
    receipt["artifacts_sha256"] = {p.name: digest(p) for p in output.iterdir() if p.is_file()}
    write_json(output / "receipt.json", receipt)
    return receipt


def verify(run, *, check_inputs=False):
    """Integrity, not authenticity or scientific validity. Receipt not self-hashed."""
    run = Path(run).resolve()
    receipt = load_json(run / "receipt.json")
    if receipt.get("engine") != ENGINE or receipt.get("status") != "completed_experimental" or receipt.get("production_release") is not False:
        raise ValueError("not a completed experimental receipt")
    artifacts = receipt.get("artifacts_sha256")
    if not artifacts:
        raise ValueError("empty artifact inventory")
    for name, expected in artifacts.items():
        if Path(name).name != name or name == "receipt.json":
            raise ValueError("unsafe artifact inventory path")
        artifact = run / name
        if artifact.is_symlink() or digest(artifact) != expected:
            raise ValueError(f"artifact integrity mismatch: {name}")
    if check_inputs:
        for name, expected in receipt["inputs_sha256"].items():
            if digest(name) != expected:
                raise ValueError(f"input integrity mismatch: {name}")
    return {"verified_artifacts": len(artifacts), "input_hashes_checked": check_inputs,
            "production_release": False}
