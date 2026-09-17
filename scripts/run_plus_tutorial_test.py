"""Official Wuhan data engineering test, not native PLUS reproduction or blind hindcast.

Uses a deterministic 120 m nearest-cell subset for a bounded first test. Static
terrain vintage is unknown. Observed 2013 quantities are an explicit oracle;
2013 is not used for suitability fitting. Never promote this to production.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import rasterio
from affine import Affine
from plus_inspired.runner import execute, write_json, write_raster, verify, digest


def run(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "inputs").mkdir()
    arrays, masks, provenance = {}, {}, []
    reference = None
    paths = {str(y): source / f"LULCs/wh{y}_refy.tif" for y in [2005, 2010, 2013]}
    paths.update({n: source / f"dringfactor/wh_df_{n}.tif" for n in ["dem", "slope"]})
    for name, path in paths.items():
        with rasterio.open(path) as src:
            if src.crs != rasterio.crs.CRS.from_epsg(32649):
                raise ValueError("official Wuhan tutorial CRS mismatch")
            grid = (src.crs, src.transform, src.shape)
            if reference is None:
                reference, profile = grid, src.profile
            if grid != reference:
                raise ValueError("source grid mismatch")
            arrays[name] = src.read(1)[::4, ::4]
            masks[name] = (src.read_masks(1)[::4, ::4] > 0) & np.isfinite(arrays[name])
            provenance.append(dict(name=name, path=str(path), sha256=digest(path),
                                   native_shape=src.shape, native_nodata=src.nodata,
                                   sampled_valid_cells=int(masks[name].sum())))
    valid = np.logical_and.reduce(list(masks.values()))
    profile.update(height=valid.shape[0], width=valid.shape[1],
                   transform=profile["transform"] * Affine.scale(4, 4))
    classes = sorted(int(x) for x in np.unique(arrays["2010"][valid]))
    for name, data in arrays.items():
        write_raster(output / f"inputs/{name}.tif", np.where(valid, data, -1), profile)
    write_raster(output / "inputs/edit.tif", np.where(valid, 1, -1), profile)
    write_raster(output / "inputs/uniform.tif", np.where(valid, 1.0, -1.0), profile)
    provenance = dict(inputs=provenance, common_valid_cells=int(valid.sum()),
                      sampled_shape=valid.shape, resolution_m=120,
                      sampling="native rows/columns 0,4,8,...; no interpolation",
                      mask="intersection of three epochs and two terrain drivers; evaluation-conditioned support",
                      demand="oracle observed 2013 class totals, NOT a forecast",
                      driver_dates="unknown; year=2005 is a static-terrain assumption, not verified vintage",
                      classes="numeric codes retained; semantic crosswalk not established")
    write_json(output / "provenance.json", provenance)
    common = dict(format="plus-inspired-config-v1", classes=classes, crs=str(reference[0]),
                  dataset_collection="official-PLUS-Wuhan-tutorial-derived-120m-v1")
    drivers = [dict(name=n, path=f"inputs/{n}.tif", year=2005, kind="continuous") for n in ["dem", "slope"]]
    configs = {
        "fit": dict(common, command="fit", initial="inputs/2005.tif", end="inputs/2010.tif",
                    origin_year=2005, end_year=2010, drivers=drivers, trees=16, seed=42),
        "predict": dict(common, command="predict", initial="inputs/2010.tif", origin_year=2010,
                        model="fit/model.json", drivers=drivers),
        "allocate": dict(common, command="allocate", initial="inputs/2010.tif", origin_year=2010,
                         target_year=2013, editable="inputs/edit.tif", seed=42, batch_size=128,
                         demand={str(c): int((arrays["2013"][valid] == c).sum()) for c in classes},
                         probabilities={str(c): f"predict/probability_{c}.tif" for c in classes},
                         transitions=np.ones((len(classes), len(classes)), dtype=int).tolist()),
        "validate": dict(format=common["format"], classes=classes, crs=common["crs"], command="validate",
                         initial="inputs/2010.tif", observed="inputs/2013.tif", simulated="allocate/land_cover.tif")}
    configs["quantity_random"] = dict(configs["allocate"],
        probabilities={str(c): "inputs/uniform.tif" for c in classes},
        patch_weight=0, stochasticity=1)
    configs["validate_random"] = dict(configs["validate"], simulated="quantity_random/land_cover.tif")
    results = {}
    for stage, config in configs.items():
        write_json(output / f"{stage}.json", config)
        try:
            receipt = execute(config["command"], output / f"{stage}.json", output / stage)
            results[stage] = dict(status=receipt["status"], integrity=verify(output / stage, check_inputs=True))
        except Exception as error:
            results[stage] = dict(status="rejected", error=str(error))
        report = (f"# Wuhan tutorial test: {stage}\n\n"
                  f"Result: `{results[stage]['status']}`.\n\n"
                  "Scope: experimental PLUS-inspired engine on official data, deterministically sampled to 120 m. "
                  "Not native PLUS equivalence, full-resolution reproduction, or blind predictive validation.\n\n"
                  "Inputs/settings: see `../provenance.json` and the corresponding stage config in the parent directory. "
                  "Terrain vintage is unverified. All transitions are allowed for this engineering probe; no policy realism claimed. "
                  "Allocation uses observed 2013 quantities. Epoch durations differ (5-year fit, 3-year allocation).\n\n"
                  f"Checks/result:\n\n```json\n{json.dumps(results[stage], indent=2)}\n```\n")
        if config["command"] == "validate" and results[stage]["status"] != "rejected":
            metrics = json.loads((output / stage / "validation.json").read_text())
            report += f"\nMetrics (including persistence):\n\n```json\n{json.dumps(metrics, indent=2)}\n```\n"
        (output / stage / "REPORT.md").write_text(report)
        print(stage, results[stage], flush=True)
        if results[stage]["status"] == "rejected":
            break
    write_json(output / "results.json", results)
    comparison = ""
    if "validate_random" in results and results["validate_random"]["status"] != "rejected":
        learned = json.loads((output / "validate/validation.json").read_text())
        random = json.loads((output / "validate_random/validation.json").read_text())
        persistence = learned["persistence_baseline"]
        comparison = "\n\n| Placement | Overall accuracy | Change Figure of Merit |\n|---|---:|---:|\n"
        for name, metrics in [("Terrain-inspired", learned), ("Persistence", persistence), ("Quantity-correct randomized net-change", random)]:
            comparison += f"| {name} | {metrics['overall_accuracy']:.2%} | {metrics['figure_of_merit']:.2%} |\n"
        comparison += ("\nInterpretation: quantity disagreement is zero by construction, not predictive success. "
                       "This engine models minimal net turnover, so it cannot reproduce all simultaneous "
                       "gains/losses observed within classes. Overall accuracy is dominated by persistent cover. "
                       "The random comparison uses the same quota/transition restrictions, one seed, no neighborhood "
                       "preference and uniform suitability; it is not an ensemble or uniform sample of every feasible map.\n")
    (output / "REPORT.md").write_text(
        "# Official Wuhan tutorial engineering test\n\n"
        "Assessment: share with caveats; no production release.\n\n"
        + "\n".join(f"- [{s}: {r['status']}]({s}/REPORT.md)" for s, r in results.items())
        + comparison
        + "\n\nSee provenance.json for grid/mask changes and source hashes. Validation metrics diagnose "
        "conditional placement only: correct future class quantities were supplied. Native Windows outputs "
        "are still needed for an implementation comparison. San Antonio held-out validation is separate.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.source, args.output)
