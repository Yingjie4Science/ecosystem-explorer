"""Offline PLUS handoff and San Antonio engineering demo; never a PLUS clone.

No dashboard equations or scenario schema are changed. Real projections enter
as externally produced PLUS rasters. The fixture only tests the artifact chain.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import html
from importlib.metadata import version
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import distance_transform_edt, label

ROOT = Path(__file__).resolve().parent
CITY = "San Antonio, TX"
NLCD = (11, 12, 21, 22, 23, 24, 31, 41, 42, 43, 52, 71, 81, 82, 90, 95)
SCHEMA = "nlcd-planning-v1"
FIXTURE_WARNING = (
    "Engineering fixture, NOT a PLUS simulation or calibrated San Antonio forecast. "
    "Future demand and allocation are illustrative. No production release is authorized."
)


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def read_raster(path, expected_crs="EPSG:5070", reference=None):
    with rasterio.open(path) as src:
        _assert_raster_crs(src, expected_crs, path)
        if src.count != 1 or not np.issubdtype(np.dtype(src.dtypes[0]), np.integer):
            raise ValueError(f"{path}: expected one-band integer categorical raster")
        if reference is not None:
            if (src.height, src.width) != (reference["height"], reference["width"]) or src.transform != reference["transform"]:
                raise ValueError(f"{path}: reference grid mismatch; align explicitly before import")
        arr = src.read(1).astype(np.int32)
        if src.nodata is not None:
            arr[arr == src.nodata] = -1
        return arr, src.profile.copy()


def _assert_raster_crs(src, expected_crs, file_path):
    if src.crs != rasterio.crs.CRS.from_user_input(expected_crs):
        raise ValueError(f"{file_path}: CRS {src.crs} != {expected_crs}")


def write_raster(path, arr, profile, dtype="int16", nodata=-1):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = profile.copy()
    profile.update(driver="GTiff", count=1, dtype=dtype, nodata=nodata, compress="deflate")
    with rasterio.open(path, "w", **profile) as dst:
        _assert_raster_crs(dst, profile["crs"], path)
        dst.write(np.asarray(arr, dtype=dtype), 1)


def write_csv(path, rows, fields):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def planning_from_nlcd(nlcd):
    out = np.full(nlcd.shape, -1, dtype=np.int16)
    unknown = set(np.unique(nlcd[nlcd >= 0])) - set(NLCD)
    if unknown:
        raise ValueError(f"Unmapped NLCD classes: {sorted(unknown)}")
    for code, nlcd_code in enumerate(NLCD, 1):
        out[nlcd == nlcd_code] = code
    return out


def validate_native(current, future, restricted, allowed):
    if current.shape != future.shape or restricted.shape != current.shape:
        raise ValueError("Array shape mismatch")
    if not np.array_equal(current < 0, future < 0):
        raise ValueError("Nodata footprint changed")
    unknown = set(np.unique(future[future >= 0])) - set(range(1, len(NLCD) + 1))
    if unknown:
        raise ValueError(f"Unknown planning classes: {sorted(unknown)}")
    changed = current != future
    if np.any(changed & restricted):
        raise ValueError("Conversion inside restricted areas")
    transitions = set(zip(current[changed].tolist(), future[changed].tolist()))
    illegal = transitions - set(allowed)
    if illegal:
        raise ValueError(f"Prohibited transitions: {sorted(illegal)}")
    return {"passed": True, "changed_cells": int(changed.sum()), "prohibited_transitions": 0,
            "restricted_conversions": 0, "nodata_footprint_preserved": True}


def expand_compound(current_planning, future, baseline, representatives):
    """Preserve all unchanged NLUD/canopy; changed cells use explicit assumptions."""
    out = baseline.copy()
    for code in np.unique(future[(future != current_planning) & (future >= 0)]):
        if int(code) not in representatives:
            raise ValueError(f"Missing compound crosswalk for planning class {code}")
        out[(future == code) & (future != current_planning)] = representatives[int(code)]
    return out


def transition_rows(current, future, cell_area_m2):
    valid = (current >= 0) & (future >= 0)
    codes, counts = np.unique(current[valid].astype(np.int64) * 100 + future[valid], return_counts=True)
    return [{"from_class": int(code // 100), "to_class": int(code % 100), "cells": int(n),
             "area_ha": float(n * cell_area_m2 / 10000)} for code, n in zip(codes, counts)]


def hindcast_metrics(current, observed, simulated):
    """Changed-cell FoM plus class-level quantity/allocation disagreement."""
    if current.shape != observed.shape or current.shape != simulated.shape:
        raise ValueError("Hindcast grid mismatch")
    if not np.array_equal(current < 0, observed < 0) or not np.array_equal(current < 0, simulated < 0):
        raise ValueError("Hindcast nodata mismatch")
    valid = current >= 0
    for arr in (current, observed, simulated):
        if set(np.unique(arr[valid])) - set(range(1, len(NLCD) + 1)):
            raise ValueError("Hindcast requires the declared planning taxonomy")
    obs_change = (observed != current) & valid
    sim_change = (simulated != current) & valid
    union = obs_change | sim_change
    hits = obs_change & sim_change & (observed == simulated)
    n = int(valid.sum())
    if n == 0:
        raise ValueError("Empty hindcast extent")
    codes = np.union1d(observed[valid], simulated[valid])
    quantity = sum(abs(int((observed[valid] == c).sum()) - int((simulated[valid] == c).sum())) for c in codes) / (2 * n)
    total = float(np.count_nonzero(observed[valid] != simulated[valid]) / n)
    classes = {}
    for code in codes:
        obs = (observed == code) & valid
        sim = (simulated == code) & valid
        tp = int((obs & sim).sum())
        classes[str(int(code))] = {"precision": tp / int(sim.sum()) if sim.any() else None,
                                  "recall": tp / int(obs.sum()) if obs.any() else None}
    return {"figure_of_merit": float(hits.sum() / union.sum()) if union.any() else None,
            "quantity_disagreement": quantity, "allocation_disagreement": max(0.0, total - quantity),
            "total_disagreement": total, "observed_change_cells": int(obs_change.sum()),
            "simulated_change_cells": int(sim_change.sum()), "valid_cells": n,
            "class_precision_recall": classes}


def quantity_correct_random(current, observed, seed, restricted=None):
    """Preserve observed transition quantities; randomize within source class."""
    if current.shape != observed.shape or not np.array_equal(current < 0, observed < 0):
        raise ValueError("Random comparator extent mismatch")
    restricted = np.zeros(current.shape, bool) if restricted is None else restricted
    if restricted.shape != current.shape or np.any((current != observed) & restricted):
        raise ValueError("Observed transitions violate comparator restrictions")
    rng = np.random.default_rng(seed)
    result = current.copy()
    for source in np.unique(current[current >= 0]):
        targets, quantities = np.unique(observed[(current == source) & (observed != current)], return_counts=True)
        pool = rng.permutation(np.flatnonzero((current == source) & ~restricted))
        offset = 0
        for target, count in zip(targets, quantities):
            result.ravel()[pool[offset:offset + count]] = target
            offset += count
    return result


def verify_run(out):
    """Detect changed/missing artifacts without recalculating any model math."""
    out = Path(out).resolve()
    manifest = json.loads((out / "manifest.json").read_text())
    if manifest["production_release_allowed"] is not False:
        raise ValueError("v1 handoff cannot authorize production release")
    for relative, expected in manifest["artifacts_sha256"].items():
        path = (out / relative).resolve()
        if not path.is_relative_to(out) or not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Missing or modified artifact: {relative}")
    return {"passed": True, "artifacts_verified": len(manifest["artifacts_sha256"]),
            "production_release_allowed": False}


def audit():
    from config import CITIES
    cfg = CITIES[CITY]
    required = {
        "compound_lulc": ROOT / cfg["data_dir_flood"] / cfg["compound_lulc_file"],
        "population": ROOT / cfg["pop_file"], "reference_et": ROOT / cfg["et_file"],
        "soil": ROOT / cfg["data_dir_flood"] / cfg["soil_file"],
        "crosswalk": ROOT / cfg["data_dir_flood"] / cfg["crosswalk_file"],
        "ucm_table": ROOT / cfg["data_dir_cooling"] / cfg["cooling_table_file"],
        "una_table": ROOT / cfg["una_table_file"], "carbon_table": ROOT / cfg["carbon_table_file"],
        "cn_table": ROOT / cfg["data_dir_flood"] / cfg["cn_table_file"],
        "food_yield_record": ROOT / "data/sa/food_forest_yield_report_2023.json",
    }
    missing = [str(p) for p in required.values() if not p.is_file()]
    return {"city": CITY, "analysis_extent": "Existing San Antonio/Bexar modeled raster extent, not city administrative boundary",
            "input_paths": {k: str(v.resolve()) for k, v in required.items()}, "missing_inputs": missing,
            "input_sha256": {k: sha256(v) for k, v in required.items() if v.is_file()},
            "current_evaluation_ready": not missing,
            "plus_execution_ready": False, "calibrated_projection_ready": False,
            "blockers": ["No verified PLUS executable/source runner configured on this host",
                         "Three comparable historical epochs and time-valid driver manifest not configured",
                         "Held-out hindcast and empirical local calibration pending",
                         "Compound expansion crosswalk requires analyst approval",
                         "License/source-build artifact pending; open-source status confirmed by author communication"]}


def prepare(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    readiness = audit()
    write_json(out / "readiness.json", readiness)
    if readiness["missing_inputs"]:
        raise ValueError(f"Missing required inputs: {readiness['missing_inputs']}")
    paths = readiness["input_paths"]
    food_record = json.loads(Path(paths["food_yield_record"]).read_text())
    write_json(out / "inputs/food_yield_record.json", food_record)
    baseline, profile = read_raster(paths["compound_lulc"])
    if profile["transform"].b != 0 or profile["transform"].d != 0 or profile["transform"].a != 30 or profile["transform"].e != -30:
        raise ValueError("San Antonio pilot requires its configured north-up 30 m grid")
    with Path(paths["crosswalk"]).open(encoding="utf-8-sig", newline="") as stream:
        compound_rows = list(csv.DictReader(stream))
    lookup = {int(r["lucode"]): int(r["nlcd"]) for r in compound_rows}
    if set(np.unique(baseline[baseline >= 0])) - lookup.keys():
        raise ValueError("Baseline contains unknown compound codes")
    nlcd = np.full(baseline.shape, -1, dtype=np.int16)
    lut = np.array([lookup[i] for i in range(max(lookup) + 1)])
    nlcd[baseline >= 0] = lut[baseline[baseline >= 0]]
    current = planning_from_nlcd(nlcd)
    rows = []
    for code, nc in enumerate(NLCD, 1):
        candidates = [r for r in compound_rows if int(r["nlcd"]) == nc]
        realistic = [r for r in candidates if r["is_realistic_to_create"].lower() == "yes"]
        chosen = max(realistic or candidates, key=lambda r: float(r["frequency"] or 0))
        rows.append({"planning_class": code, "nlcd": nc, "label": chosen["nlcd_lulc"],
                     "representative_compound_lucode": int(chosen["lucode"]),
                     "assumed_nlud": chosen["nlud_simple"], "assumed_tree_tier": chosen["tree"],
                     "reviewed": "false"})
    write_csv(out / "inputs/planning_classes.csv", rows, list(rows[0]))
    write_raster(out / "inputs/current_planning.tif", current, profile)
    # Deliberate provisional rule set; not a claim about San Antonio zoning.
    restricted = (current < 0) | np.isin(nlcd, [11, 12, 90, 95])
    write_raster(out / "inputs/restricted.tif", restricted, profile, "uint8", 255)
    allowed = [(i, i) for i in range(1, 17)] + [(NLCD.index(nc) + 1, NLCD.index(22) + 1) for nc in (52, 71, 81, 82)]
    write_csv(out / "inputs/allowed_transitions.csv", [{"from_class": a, "to_class": b} for a, b in allowed], ["from_class", "to_class"])
    demand = [{"planning_class": int(c), "current_cells": int(n), "target_cells": int(n)}
              for c, n in zip(*np.unique(current[current >= 0], return_counts=True))]
    write_csv(out / "inputs/demand_template.csv", demand, list(demand[0]))
    write_json(out / "inputs/engine_record.template.json", {
        "name": "PLUS", "version": "REQUIRED", "source_or_binary_sha256": "REQUIRED",
        "runner": "REQUIRED", "license_evidence": "REQUIRED", "parameters_path": "REQUIRED",
        "native_log_path": "REQUIRED", "target_year": 2030, "seed": 42,
        "role": "plus_bau", "hindcast_approved": False, "crosswalk_approved": False,
        "demand_path": "REQUIRED", "demand_approved": False})
    write_json(out / "inputs/historical_inputs.template.json", {
        "epochs": [{"year": y, "raster": "REQUIRED", "source_product_version": "REQUIRED"} for y in (2011, 2016, 2021)],
        "driver_manifest": "REQUIRED", "note": "Use one comparable product series; do not invent epochs from current LULC."})
    return baseline.astype(np.int16), current, restricted, allowed, rows, profile


def fixture_future(current, cells, seed):
    """Deterministic growth stress fixture; not LEAS/CARS, demand or zoning."""
    if cells <= 0:
        raise ValueError("growth cells must be positive")
    developed = np.isin(current, [NLCD.index(c) + 1 for c in (21, 22, 23, 24)])
    candidates = np.flatnonzero(np.isin(current, [NLCD.index(c) + 1 for c in (52, 71, 81, 82)]))
    if len(candidates) < cells:
        raise ValueError("Insufficient growth-fixture candidates")
    distance = distance_transform_edt(~developed).ravel()[candidates]
    score = distance + np.random.default_rng(seed).uniform(0, 2, len(candidates))
    chosen = candidates[np.argsort(score, kind="stable")[:cells]]
    future = current.copy()
    future.ravel()[chosen] = NLCD.index(22) + 1
    return future


def load_engine_record(path):
    path = Path(path).resolve()
    record = json.loads(path.read_text())
    for key in ("name", "version", "source_or_binary_sha256", "runner", "license_evidence", "parameters_path", "native_log_path", "target_year", "seed", "role", "demand_path"):
        if key not in record or record[key] in ("", "REQUIRED", None):
            raise ValueError(f"Engine record field {key} is required")
    if record["name"] != "PLUS" or record["role"] not in ("plus_bau", "plus_policy", "plus_hindcast"):
        raise ValueError("External raster must carry a PLUS engine and explicit PLUS role")
    if len(record["source_or_binary_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in record["source_or_binary_sha256"]):
        raise ValueError("Engine source/binary SHA256 must be 64 lowercase hex characters")
    for key in ("parameters_path", "native_log_path", "demand_path"):
        source = Path(record[key])
        source = source if source.is_absolute() else path.parent / source
        if not source.is_file():
            raise ValueError(f"Missing engine evidence: {key}: {source}")
        record[key] = str(source.resolve())
    return record


def package_native(out, baseline, current, future, restricted, allowed, rows, profile, engine):
    qc = validate_native(current, future, restricted, allowed)
    if engine["name"] == "PLUS":
        with Path(engine["demand_path"]).open(newline="") as stream:
            demand_rows = list(csv.DictReader(stream))
        expected = {int(r["planning_class"]): int(r["target_cells"]) for r in demand_rows}
        if len(expected) != len(demand_rows) or any(c not in range(1, 17) or n < 0 for c, n in expected.items()):
            raise ValueError("Demand must have unique planning classes 1..16 and nonnegative counts")
        actual = {int(c): int(n) for c, n in zip(*np.unique(future[future >= 0], return_counts=True))}
        if any(actual.get(c, 0) != expected.get(c, 0) for c in set(expected) | set(actual)):
            raise ValueError("PLUS output does not meet declared demand counts")
        qc["demand_counts_match"] = True
    representatives = {r["planning_class"]: r["representative_compound_lucode"] for r in rows}
    compound = expand_compound(current, future, baseline, representatives)
    write_raster(out / "canonical/lulc_future.tif", future, profile)
    change = np.where(current >= 0, current.astype(np.int32) * 100 + future, -1)
    write_raster(out / "canonical/lulc_change.tif", change, profile)
    area = abs(profile["transform"].a * profile["transform"].e)
    tr = transition_rows(current, future, area)
    write_csv(out / "canonical/transition_counts.csv", tr, ["from_class", "to_class", "cells", "area_ha"])
    write_json(out / "canonical/qc.json", qc)
    write_raster(out / "invest/compound_future.tif", compound, profile)
    audit_rows = [dict(r, changed_cells=int(np.count_nonzero((future == r["planning_class"]) & (future != current)))) for r in rows]
    write_csv(out / "invest/crosswalk_audit.csv", audit_rows, list(audit_rows[0]))
    return compound, qc


def load_evaluator():
    # Existing regression harness supplies the offline interface. No GUI writes.
    from verify_baselines import _StubSt, _rebind_city
    sys.modules["streamlit"] = _StubSt()
    import app
    _rebind_city(app, CITY)
    state = app._CURRENT_CITY_STATE
    if not state.population_data_available or not state.et_data_available or state.cooling_lulc_compound is None:
        raise ValueError("Required downstream evaluator inputs unavailable")
    return app, state


def evaluate(app, state, compound, baseline):
    nlcd = app.reduce_compound_to_nlcd(compound, state.compound_to_nlcd)
    cn = app._per_pixel_cn(nlcd, compound, state.compound_to_nlcd_tree, state.lucode_idx_arr, state.cn_table, state.soil_resized)
    hmi = app._compute_hmi_raster_pure(compound, state.shade_arr, state.kc_arr, state.albedo_arr,
                                       state.et_resized, state.max_et_ref, state.green_area_arr)
    valid = (compound >= 0) & np.isfinite(hmi)
    pop = np.where(valid, state.pop_count_raster, 0)
    if pop.sum() <= 0:
        raise ValueError("No modelable population")
    supply, una_valid = app._una_supply_percapita_pure(compound, pop, state.urban_nature_arr)
    adequate = una_valid & (supply >= app.UNA_DEMAND_M2_PER_CAPITA)
    ndvi = app._lulc_to_ndvi_raster(nlcd)
    baseline_ne = app._umh_neighborhood_exposure(app._lulc_to_ndvi_raster(app.reduce_compound_to_nlcd(baseline, state.compound_to_nlcd)))
    mh, _ = app.calculate_mental_health_impact(nlcd, baseline_ne, pop, ndvi_raster=ndvi)
    result = {
        "hmi_area_mean": float(hmi[valid].mean()),
        "hmi_population_weighted_mean": float(np.nansum(hmi * pop) / pop.sum()),
        "runoff_retention_index": app.cn_array_to_retention_index(cn, (cn > 0) & valid),
        "adequate_nature_access_population_pct": float(100 * pop[adequate].sum() / pop.sum()),
        "carbon_stock_delta_t_co2": app._compute_carbon_four_pool_pure(compound, baseline, state.c_above_arr, state.c_below_arr, state.c_soil_arr, state.c_dead_arr),
        "preventable_mh_case_events_proxy_vs_A": mh,
        "fixed_modelable_population": float(pop.sum()),
    }
    # Fixed present-day population and NDVI/prevalence proxies are explicit.
    return result, hmi, nlcd


def food_yield_capacity(cells, cell_area_m2, record, establishment_fraction=1.0):
    if not 0 <= establishment_fraction <= 1:
        raise ValueError("Food establishment fraction must be in [0, 1]")
    if cells < 0 or cell_area_m2 <= 0:
        raise ValueError("Invalid food-forest area")
    acres = cells * cell_area_m2 / 4046.8564224
    rows = [{"crop": r["crop"], "yield_capacity_lbs_year":
             acres * r["reported_discounted_lbs_quarter_acre_year"] * establishment_fraction}
            for r in record["crops"]]
    return float(sum(r["yield_capacity_lbs_year"] for r in rows)), rows


def bundle(app, state, compound, parent, profile, scenario_id, engine):
    import export_invest_bundle as eib
    from config import CITIES
    cfg = CITIES[CITY]
    spec = eib.BundleSpec(
        city_name=CITY, city_slug="san_antonio_tx", crs=cfg["crs"], pixel_size_m=30,
        scenario_id=scenario_id, scenario_label=scenario_id,
        scenario_description="Offline PLUS handoff demo; " + (FIXTURE_WARNING if engine["name"] != "PLUS" else "Analyst review pending"),
        provenance="Engineering fixture" if engine["name"] != "PLUS" else "PLUS conditional projection — review pending",
        generator=engine, git_commit=git_commit(), scenario_schema_version=app.SCENARIO_SCHEMA_VERSION,
        is_sa=True, raster_profile=profile, scenario_lulc_compound=compound, baseline_lulc_compound=parent,
        scenario_lulc_nlcdtree=app.reduce_compound_to_nlcd_tree(compound, state.compound_to_nlcd_tree),
        baseline_lulc_nlcdtree=app.reduce_compound_to_nlcd_tree(parent, state.compound_to_nlcd_tree),
        scenario_ndvi=app._lulc_to_ndvi_raster(app.reduce_compound_to_nlcd(compound, state.compound_to_nlcd)),
        baseline_ndvi=app._lulc_to_ndvi_raster(app.reduce_compound_to_nlcd(parent, state.compound_to_nlcd)),
        pop_path=str(ROOT / cfg["pop_file"]), et_path=str(ROOT / cfg["et_file"]),
        soil_path=str(ROOT / cfg["data_dir_flood"] / cfg["soil_file"]), block_groups_path=str(ROOT / cfg["tracts_file"]),
        ucm_table_path=str(ROOT / cfg["data_dir_cooling"] / cfg["cooling_table_file"]),
        una_table_path=str(ROOT / cfg["una_table_file"]), carbon_table_path=str(ROOT / cfg["carbon_table_file"]),
        cn_table_path=str(ROOT / cfg["data_dir_flood"] / cfg["cn_table_file"]),
        uhi_max_c=cfg["uhi_max_c"], una_demand_m2=cfg["una_demand_m2_per_capita"],
        una_radius_m=int(cfg["una_search_radius_m"]), una_decay=cfg["una_decay_function"],
        design_storm_mm=round(cfg["design_storm_inches"] * 25.4, 1))
    return eib.build_invest_bundle(spec)


def finalize(out, engine, qc, results, contrasts, footprint_cells):
    readiness = json.loads((out / "readiness.json").read_text())
    # Approval booleans alone are not validation evidence: no release in v1.
    manifest = {"schema_version": 1, "class_schema_id": SCHEMA, "city": CITY,
                "engine": engine, "git_commit": git_commit(), "python": sys.version,
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "platform": platform.platform(), "qc": qc,
                "dependency_versions": {name: version(name) for name in ("numpy", "scipy", "rasterio", "pandas", "geopandas", "matplotlib", "scikit-image")},
                "production_release_allowed": False, "review_status": "engineering-demo-only" if engine["name"] != "PLUS" else "external-plus-import-review-pending",
                "readiness": readiness, "intervention_cells": footprint_cells,
                "fixed_population_vintage": 2020,
                "aggregation": "Existing modeled extent; fixed population; area and population HMI means kept separate",
                "metric_caveats": ["HMI is an index, not UTCI, WBGT or directly validated thermal exposure",
                                  "MH uses NLCD-derived NDVI and assumed prevalence; events are not unique persons",
                                  "Carbon is one-time stock change, not annual sequestration",
                                  "Compound NLUD/canopy expansion is an unreviewed scenario assumption",
                                  "Mature food-forest conversion does not model establishment lag",
                                  "Population, climate, roads, buildings and ownership held fixed; no socioeconomic forecast",
                                  "Canonical bundles are handoffs, not evidence of independently executed canonical runs"],
                "results": results, "contrasts": contrasts}
    manifest["scenario_lineage"] = {
        "A_current": {"role": "observed_derived_current", "parent": "input compound baseline"},
        "B_current_food_forest": {"role": "planner_intervention", "parent": "A_current"},
        "C_background": {"role": engine["role"], "parent": "A_current"},
        "D_background_food_forest": {"role": "combined_test_fixture" if engine["name"] != "PLUS" else "combined_review_pending", "parent": "C_background"}}
    manifest["source_sha256"] = {str(p.relative_to(ROOT)): sha256(p) for p in
                                 (ROOT / "plus_workflow.py", ROOT / "app.py", ROOT / "config.py", ROOT / "export_invest_bundle.py")}
    manifest["food_source"] = json.loads((out / "inputs/food_yield_record.json").read_text())
    manifest["eligibility_caveats"] = ["Engineering placement uses NLCD 21-23 and raster public ownership classes 1-4",
                                      "Original project's underutilized-natural-land and city-boundary screens are not reproduced",
                                      "Parcel minimum area, utility ownership and military/airport exclusions are not reproduced",
                                      "30 m ownership is a planning approximation, not verified parcel eligibility"]
    manifest["artifacts_sha256"] = {str(p.relative_to(out)): sha256(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "manifest.json"}
    write_json(out / "manifest.json", manifest)


def run(out, native=None, engine_record=None, growth_cells=2000, intervention_cells=1000, seed=42, make_bundles=True, food_establishment_fraction=1.0):
    out = Path(out).resolve()
    engine = load_engine_record(engine_record) if native else {"name": "engineering_fixture", "algorithm": "distance-to-developed growth stress fixture, NOT LEAS/CARS",
                                                             "growth_cells": growth_cells, "seed": seed, "target_year": None, "role": "test_fixture"}
    baseline, current, restricted, allowed, rows, profile = prepare(out)
    if native:
        future, _ = read_raster(native, reference=profile)
        (out / "plus_native").mkdir()
        shutil.copy2(native, out / "plus_native/lulc_future.tif")
        for key in ("parameters_path", "native_log_path", "demand_path"):
            shutil.copy2(engine[key], out / "plus_native" / (key + Path(engine[key]).suffix))
        write_json(out / "plus_native/engine_record.json", engine)
    else:
        future = fixture_future(current, growth_cells, seed)
        write_raster(out / "fixture_native/lulc_future.tif", future, profile)
        write_json(out / "fixture_native/generator.json", engine)
    compound_future, qc = package_native(out, baseline, current, future, restricted, allowed, rows, profile, engine)
    print("Importing existing evaluator and loading San Antonio...", flush=True)
    app, state = load_evaluator()
    if not np.array_equal(baseline, state.cooling_lulc_compound):
        raise ValueError("Evaluator baseline differs from handoff baseline")
    # Same footprint for B and D; eligible under BOTH backgrounds, no structures.
    eligible = np.zeros(baseline.shape, dtype=bool)
    eligible[tuple(state.convertible_pixels.T)] = True
    future_nlcd = app.reduce_compound_to_nlcd(compound_future, state.compound_to_nlcd)
    eligible &= np.isin(future_nlcd, app.DEVELOPED_CODES)
    eligible &= ~restricted
    if state.ownership_raster is None:
        raise ValueError("San Antonio public-ownership input required")
    eligible &= np.isin(state.ownership_raster, [1, 2, 3, 4])
    candidates = np.flatnonzero(eligible)
    if intervention_cells <= 0 or len(candidates) < intervention_cells:
        raise ValueError(f"Need {intervention_cells} intervention cells; {len(candidates)} eligible")
    ranking = state.baseline_hm_raster.ravel()[candidates]
    chosen = candidates[np.argsort(ranking, kind="stable")[:intervention_cells]]
    mask = np.zeros(baseline.shape, dtype=bool)
    mask.ravel()[chosen] = True
    scenarios = {"A_current": baseline, "C_background": compound_future}
    fallback = {}
    for parent, child in (("A_current", "B_current_food_forest"), ("C_background", "D_background_food_forest")):
        arr = scenarios[parent].copy()
        source = arr[mask]
        arr[mask] = state.compound_after_ff[source]
        fallback[child] = int(state.compound_after_ff_was_default[source].sum())
        scenarios[child] = arr
    write_raster(out / "canonical/intervention_footprint.tif", mask, profile, "uint8", 255)
    qc["intervention_subset_eligible"] = bool(np.all(~mask | eligible))
    qc["matched_intervention_cells"] = intervention_cells
    qc["food_forest_crosswalk_fallback_cells"] = fallback
    write_json(out / "canonical/qc.json", qc)
    food_record = json.loads((out / "inputs/food_yield_record.json").read_text())
    food_total, food_rows = food_yield_capacity(intervention_cells, 900, food_record, food_establishment_fraction)
    write_csv(out / "review/food_yield_by_crop.csv", food_rows, list(food_rows[0]))
    engine["intervention"] = {"type": "food_forest", "cells": intervention_cells,
                              "placement": "current HMI ranked; fixed matched footprint; public ownership classes 1/2/3/4",
                              "food_establishment_fraction": food_establishment_fraction}
    engine["evaluator"] = {"name": "Explorer existing model-aligned functions", "scenario_schema_version": app.SCENARIO_SCHEMA_VERSION,
                           "independent_canonical_runs_performed": False}
    results, hmis = {}, {}
    for name in ("A_current", "B_current_food_forest", "C_background", "D_background_food_forest"):
        print(f"Evaluating {name}...", flush=True)
        arr = scenarios[name]
        results[name], hmi, nlcd = evaluate(app, state, arr, baseline)
        results[name]["intervention_food_yield_capacity_lbs_year"] = food_total if name.startswith(("B_", "D_")) else 0.0
        hmis[name] = hmi
        write_raster(out / f"invest/{name}/ucm_lulc.tif", arr, profile)
        write_raster(out / f"invest/{name}/una_lulc.tif", arr, profile)
        write_raster(out / f"invest/{name}/carbon_lulc.tif", arr, profile)
        write_raster(out / f"invest/{name}/ufr_lulc.tif", app.reduce_compound_to_nlcd_tree(arr, state.compound_to_nlcd_tree), profile, nodata=-128)
        write_raster(out / f"review/{name}_hmi.tif", np.where(np.isfinite(hmi), hmi, -9999), profile, "float32", -9999)
        write_raster(out / f"canonical/{name}_nlcd.tif", nlcd, profile, nodata=-128)
        if make_bundles:
            parent = scenarios["C_background"] if name == "D_background_food_forest" else baseline
            (out / f"invest/{name}/canonical_invest_bundle.zip").write_bytes(bundle(app, state, arr, parent, profile, name, engine))
    contrasts = {}
    for title, after, before in (("background_change_C_minus_A", "C_background", "A_current"),
                                  ("current_intervention_B_minus_A", "B_current_food_forest", "A_current"),
                                  ("future_intervention_D_minus_C", "D_background_food_forest", "C_background")):
        delta = {k: results[after][k] - results[before][k] for k in results[before] if k != "fixed_modelable_population"}
        # MH is nonlinear: use the explicit paired exposure baseline, rather
        # than subtracting rounded preventable events both referenced to A.
        before_nlcd = app.reduce_compound_to_nlcd(scenarios[before], state.compound_to_nlcd)
        before_ne = app._umh_neighborhood_exposure(app._lulc_to_ndvi_raster(before_nlcd))
        after_nlcd = app.reduce_compound_to_nlcd(scenarios[after], state.compound_to_nlcd)
        paired_mh, _ = app.calculate_mental_health_impact(after_nlcd, before_ne, state.pop_count_raster)
        delta.pop("preventable_mh_case_events_proxy_vs_A")
        delta["paired_preventable_mh_case_events_proxy"] = paired_mh
        delta["temperature_index_delta_c"] = -delta["hmi_area_mean"] * app.UHI_MAX_C
        contrasts[title] = delta
    write_csv(out / "review/scenario_metrics.csv", [dict(scenario=k, **v) for k, v in results.items()], ["scenario"] + list(next(iter(results.values()))))
    write_csv(out / "review/contrasts.csv", [dict(contrast=k, **v) for k, v in contrasts.items()], ["contrast"] + list(next(iter(contrasts.values()))))
    patches = []
    for name, arr in (("background_change", current != future), ("food_forest_footprint", mask)):
        labels, n = label(arr)
        sizes = np.bincount(labels.ravel())[1:]
        patches.append({"layer": name, "patches_4_connected": int(n), "largest_patch_cells": int(sizes.max()) if n else 0})
    write_csv(out / "review/patch_metrics.csv", patches, list(patches[0]))
    create_report(out, scenarios, hmis, contrasts, engine, profile)
    write_json(out / "review/reviewer_decision.json", {"decision": "not-released", "reason": "Upstream calibration, crosswalk and analyst review pending", "reviewer": None})
    finalize(out, engine, qc, results, contrasts, intervention_cells)
    write_json(out / "integrity_check.json", verify_run(out))
    print(f"Completed engineering handoff: {out / 'review/report.html'}", flush=True)
    return out


def create_report(out, scenarios, hmis, contrasts, engine, profile):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    for ax, name in zip(axes.ravel(), ("A_current", "B_current_food_forest", "C_background", "D_background_food_forest")):
        image = ax.imshow(hmis[name][::4, ::4], vmin=0, vmax=1, cmap="YlGnBu", interpolation="nearest")
        ax.set_title(name.replace("_", " "))
        ax.set_axis_off()
    fig.colorbar(image, ax=axes, label="Heat mitigation index (not air temperature)", shrink=.7)
    fig.savefig(out / "review/map_overview.png", dpi=130)
    plt.close(fig)
    changed = scenarios["A_current"] != scenarios["C_background"]
    intervention = scenarios["A_current"] != scenarios["B_current_food_forest"]
    overview = np.zeros(changed.shape, dtype=np.uint8)
    overview[changed] = 1
    overview[intervention] = 2
    fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)
    ax.imshow(overview, vmin=0, vmax=2, cmap=matplotlib.colors.ListedColormap(["#eeeeee", "#e66101", "#1b9e77"]))
    ax.set_title("Orange: test background growth; green: matched food-forest footprint")
    ax.set_axis_off()
    fig.savefig(out / "review/change_map.png", dpi=150)
    plt.close(fig)
    headers = list(next(iter(contrasts.values())))
    table = "<tr><th>Contrast</th>" + "".join(f"<th>{html.escape(k)}</th>" for k in headers) + "</tr>"
    for name, values in contrasts.items():
        table += f"<tr><th>{html.escape(name)}</th>" + "".join(f"<td>{v:.6g}</td>" for v in values.values()) + "</tr>"
    warning = FIXTURE_WARNING if engine["name"] != "PLUS" else "External PLUS output imported; production review remains pending."
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>San Antonio PLUS handoff demo</title>
<style>body{{font:16px system-ui;max-width:1200px;margin:40px auto;padding:0 20px;color:#243b42}} .warning{{background:#fff1cf;padding:20px;border-left:5px solid #b97900}} img{{max-width:100%}} table{{border-collapse:collapse;font-size:12px}}td,th{{padding:10px;border:1px solid #ccc}}.scroll{{overflow:auto}}a{{color:#086873}}</style>
<h1>San Antonio: land-change → intervention → Urban InVEST</h1><p class="warning">{html.escape(warning)}</p>
<p>Existing San Antonio/Bexar modeled extent, EPSG:5070, 30 m. This is not the city administrative boundary. Population, climate and infrastructure are held fixed.</p>
<h2>Matched four-scenario experiment</h2><p>A: current; B: current + food forest; C: background; D: background + the same food-forest footprint. Background C−A, present intervention B−A, future intervention D−C. D−A is deliberately not reported as intervention benefit.</p>
<img src="map_overview.png" alt="Four heat-mitigation maps"><img src="change_map.png" alt="Background changes and matched intervention footprint">
<h2>Contrasts</h2><div class="scroll"><table>{table}</table></div>
<p>Temperature-index delta is −11 × area-mean HMI delta, not independently run canonical T_air, UTCI or WBGT. Nature-access deltas are percentage points. Carbon is a one-time stock change. Mental-health case events use proxy NDVI/prevalence and are not unique people.</p>
<h2>Food production capacity</h2><p>The food module uses the four discounted per-crop entries in the supplied 2023 report, Table A2-4. Their sum is 11,438 lb/acre/year, versus 11,483 in the narrative (45 lb discrepancy, review pending). Mature productivity and equal crop shares are assumptions. This is intervention capacity only, not total city production or net food change from background growth. The dashboard's existing yield scalar is unchanged.</p><p><a href="food_yield_by_crop.csv">Per-crop food capacity</a> / <a href="../inputs/food_yield_record.json">Source and discrepancy record</a></p>
<h2>Eligibility boundary</h2><p>This engineering screen uses current convertible developed pixels (NLCD 21–23), structural exclusions and rasterized public ownership classes 1–4, then ranks by current HMI. It does not reproduce the project's city-boundary/underutilized-natural-land/parcel-size screen, utility ownership, or military/airport exclusions. It is not a parcel recommendation.</p>
<h2>Evidence and handoff</h2><ul><li><a href="../manifest.json">Run manifest, input/output hashes and caveats</a></li><li><a href="../readiness.json">Readiness and upstream blockers</a></li><li><a href="../canonical/qc.json">QC checks</a></li><li><a href="scenario_metrics.csv">Scenario metrics</a></li><li><a href="contrasts.csv">Contrasts</a></li><li><a href="../invest/crosswalk_audit.csv">Compound expansion assumptions</a></li></ul>
<p>Four canonical InVEST bundles are available under invest/[scenario]/ when requested. They have not been independently executed by this demo. The evaluator reuses existing Explorer functions; algorithmic parity does not establish empirical local validation.</p>
<h2>Next gate</h2><p>Obtain the author-supported PLUS runner/source build, one comparable three-epoch LULC series and time-valid drivers; train LEAS, hindcast with CARS, validate against persistence/random/CLUE and assess ensembles before releasing a conditional projection.</p></html>'''
    (out / "review/report.html").write_text(page)
