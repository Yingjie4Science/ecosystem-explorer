"""Small manufactured-landscape end-to-end example, not San Antonio data."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from rasterio.transform import from_origin
from rasterio.crs import CRS

from plus_inspired.runner import execute, write_json, write_raster, verify


def demo(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "inputs"
    inputs.mkdir()
    row, col = np.indices((64, 64))
    valid = np.ones((64, 64), bool)
    valid[-1] = False
    start = np.full((64, 64), 71, np.int16)
    start[:4] = 21
    start[:, :4] = 11
    end = start.copy()
    end[4:12, 4:32] = 21
    observed = end.copy()
    observed[4:12, 32:60] = 21
    edit = valid & (end == 71)
    profile = dict(driver="GTiff", height=64, width=64, count=1, dtype="int16", crs=CRS.from_epsg(5070),
                   transform=from_origin(0, 1920, 30, 30), nodata=-1)
    for name, array in [("start", start), ("end", end), ("observed", observed), ("row", row.astype(np.float32)),
                        ("edit", edit.astype(np.int16))]:
        write_raster(inputs / f"{name}.tif", np.where(valid, array, -1), profile)
    common = dict(format="plus-inspired-config-v1", classes=[11, 21, 71], crs="EPSG:5070",
                  dataset_collection="manufactured-landscape-v1")
    drivers = [dict(name="row", path="inputs/row.tif", year=2005, kind="continuous")]
    fit = dict(common, command="fit", initial="inputs/start.tif", end="inputs/end.tif",
               origin_year=2005, end_year=2015, drivers=drivers, trees=16, seed=42)
    predict = dict(common, command="predict", initial="inputs/end.tif", origin_year=2015,
                   model="fit/model.json", drivers=drivers)
    demand = {str(c): int((end[valid] == c).sum()) for c in common["classes"]}
    demand["21"] += 224
    demand["71"] -= 224
    allocate = dict(common, command="allocate", initial="inputs/end.tif", origin_year=2015,
                    target_year=2025, editable="inputs/edit.tif", demand=demand,
                    probabilities={str(c): f"predict/probability_{c}.tif" for c in common["classes"]},
                    transitions=[[1, 0, 0], [0, 1, 0], [0, 1, 1]], seed=42, batch_size=16)
    validate = dict(format=common["format"], classes=common["classes"], crs=common["crs"], command="validate",
                    initial="inputs/end.tif", observed="inputs/observed.tif", simulated="allocate/land_cover.tif")
    for command, config in [("fit", fit), ("predict", predict), ("allocate", allocate), ("validate", validate)]:
        path = output / f"{command}.json"
        write_json(path, config)
        execute(command, path, output / command)
        verify(output / command, check_inputs=True)
    write_json(output / "README.json", {"scope": "synthetic software smoke test, NOT an empirical hindcast or a 2050 projection",
                                         "production_release": False, "all_four_stages_integrity_checked": True})
    print(f"Synthetic example completed: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    demo(parser.parse_args().output)
