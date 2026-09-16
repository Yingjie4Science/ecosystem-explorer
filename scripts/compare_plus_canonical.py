#!/usr/bin/env python3
"""Input-matched demo smoke comparison; does not change the parity registry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import rasterio
import plus_workflow as workflow


def read_float(path, reference=None):
    with rasterio.open(path) as src:
        workflow._assert_raster_crs(src, "EPSG:5070", path)
        if reference and ((src.height, src.width) != (reference["height"], reference["width"]) or src.transform != reference["transform"]):
            raise ValueError(f"Canonical output grid mismatch: {path}")
        arr = src.read(1).astype(np.float64)
        valid = np.isfinite(arr)
        if src.nodata is not None:
            valid &= arr != src.nodata
        return arr, valid, src.profile.copy()


def carbon_density_to_co2(density_values, cell_ha):
    """Integrate t C/ha over hectares, then convert C mass to CO2 mass."""
    return float(np.asarray(density_values, dtype=np.float64).sum() * cell_ha * 44 / 12)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--scenario", choices=("A_current", "B_current_food_forest", "C_background", "D_background_food_forest"), required=True)
    args = parser.parse_args()
    workflow.verify_run(args.demo)
    manifest = json.loads((args.demo / "manifest.json").read_text())
    receipt = json.loads((args.canonical / "execution_receipt.json").read_text())
    if receipt["invest_version"] != "3.20.2":
        raise ValueError("This smoke comparator is verified for InVEST 3.20.2 only; audit output units before changing the version")
    bundle = args.demo / "invest" / args.scenario / "canonical_invest_bundle.zip"
    if workflow.sha256(bundle) != receipt["bundle_sha256"]:
        raise ValueError("Canonical execution did not use this scenario's bundle")
    if any(receipt["models"].get(name, {}).get("status") != "completed" for name in ("cooling", "flood", "carbon", "nature", "mh_depression", "mh_anxiety")):
        raise ValueError("All six canonical model executions are required for this comparison")
    expected = manifest["results"][args.scenario]
    hmi, valid, profile = read_float(args.demo / "review" / f"{args.scenario}_hmi.tif")
    canonical_hmi, canonical_valid, _ = read_float(args.canonical / "workspace_cooling/hm_ee_export.tif", profile)
    if not np.array_equal(valid, canonical_valid):
        raise ValueError("HMI common-extent mismatch")
    error = np.abs(hmi[valid] - canonical_hmi[valid])
    checks = {"hmi": {"mae": float(error.mean()), "max_abs_error": float(error.max()), "passed": bool(error.mean() <= 1e-4), "valid_cells": int(valid.sum())}}
    retention, rt_valid, _ = read_float(args.canonical / "workspace_flood/Runoff_retention_index_ee_export.tif", profile)
    rt_mean = float(retention[rt_valid].mean())
    checks["ufr_mean_retention"] = {"canonical": rt_mean, "explorer": expected["runoff_retention_index"], "passed": abs(rt_mean - expected["runoff_retention_index"]) <= 1e-4}
    carbon, c_valid, _ = read_float(args.canonical / "workspace_carbon/c_change_bas_alt_ee_export.tif", profile)
    # InVEST 3.20.2 declares c_change_bas_alt in metric tonnes C/ha,
    # not tonnes per pixel. Integrate density over pixel hectares first.
    cell_ha = abs(profile["transform"].a * profile["transform"].e) / 10000
    carbon_co2 = carbon_density_to_co2(carbon[c_valid], cell_ha)
    contrast = manifest["contrasts"]["future_intervention_D_minus_C"] if args.scenario.startswith("D_") else None
    expected_carbon = contrast["carbon_stock_delta_t_co2"] if contrast else expected["carbon_stock_delta_t_co2"]
    checks["carbon_stock_delta_t_co2"] = {"canonical": carbon_co2, "explorer": expected_carbon, "native_units": "t C/ha", "cell_ha": cell_ha,
                                        "passed": bool(np.isclose(carbon_co2, expected_carbon, rtol=1e-4, atol=.2))}
    supply, supply_valid, _ = read_float(args.canonical / "workspace_nature/output/urban_nature_supply_percapita_ee_export.tif", profile)
    pop, pop_valid, _ = read_float(args.canonical / "workspace_nature/intermediate/masked_population_ee_export.tif", profile)
    nature_config = json.loads((args.canonical / "nature_resolved_args.json").read_text())
    common = supply_valid & pop_valid
    access = float(100 * pop[common & (supply >= float(nature_config["urban_nature_demand"]))].sum() / pop[common].sum())
    checks["nature_access_pct"] = {"canonical": access, "explorer": expected["adequate_nature_access_population_pct"], "passed": abs(access - expected["adequate_nature_access_population_pct"]) <= .01}
    cases = 0.0
    mh_grids = {}
    for condition in ("depression", "anxiety"):
        # Canonical UMH pads/clips the NDVI search neighborhood and has its
        # own output grid. Aggregate native case totals; do not interpolate
        # counts or imply cellwise parity on a different grid.
        arr, arr_valid, mh_profile = read_float(args.canonical / f"workspace_mh_{condition}/output/preventable_cases_ee_export_{condition}.tif")
        mh_grids[condition] = {"height": mh_profile["height"], "width": mh_profile["width"], "transform": list(mh_profile["transform"])}
        cases += float(arr[arr_valid].sum())
    expected_mh = contrast["paired_preventable_mh_case_events_proxy"] if contrast else expected["preventable_mh_case_events_proxy_vs_A"]
    checks["paired_mh_proxy_case_events"] = {"canonical": cases, "explorer": expected_mh, "passed": bool(np.isclose(cases, expected_mh, rtol=.02, atol=.2)),
                                            "comparison": "Native canonical totals; padding/edge differences; not cellwise parity", "native_grids": mh_grids}
    result = {"scenario": args.scenario, "invest_version": receipt["invest_version"],
              "bundle_sha256": receipt["bundle_sha256"], "checks": checks,
              "passed": all(c["passed"] for c in checks.values()), "production_release_allowed": False,
              "claim": "Input-matched scenario smoke comparison only; no change to the project's 3.19.0 baseline parity registry"}
    workflow.write_json(args.canonical / "smoke_comparison.json", result)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
