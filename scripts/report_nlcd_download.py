"""QA three raw USGS Annual NLCD responses; acquisition QA is not model validation."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import rasterio


def report(paths, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    records, arrays, masks = [], [], []
    expected = {11, 12, 21, 22, 23, 24, 31, 41, 42, 43, 52, 71, 81, 82, 90, 95}
    grid = None
    for year, path in zip([2005, 2015, 2025], paths):
        path = Path(path).resolve()
        with rasterio.open(path) as src:
            if src.crs != rasterio.crs.CRS.from_epsg(5070):
                raise ValueError("NLCD analysis CRS mismatch")
            this_grid = (src.crs, src.transform, src.shape)
            if grid is not None and grid != this_grid:
                raise ValueError("epoch grid mismatch")
            grid = this_grid
            data = src.read(1)
            valid = (src.read_masks(1) > 0) & (data != 0)
            codes, counts = np.unique(data[valid], return_counts=True)
            if src.count != 1 or not np.allclose(src.res, (30.0, 30.0), rtol=0, atol=1e-6) or not set(codes).issubset(expected):
                raise ValueError("not a native-resolution categorical land-cover response")
            arrays.append(data)
            masks.append(valid)
            records.append(dict(year_requested=year, path=str(path),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), shape=src.shape,
                crs=str(src.crs), transform=list(src.transform), resolution_m=src.res,
                nodata=src.nodata, valid_cells=int(valid.sum()),
                class_counts={str(int(c)): int(n) for c, n in zip(codes, counts)},
                tags=src.tags()))
    valid = np.logical_and.reduce(masks)
    changes = {f"{a}-{b}": int(((arrays[i] != arrays[i+1]) & valid).sum())
               for i, (a, b) in enumerate([(2005, 2015), (2015, 2025)])}
    if not all(changes.values()):
        raise ValueError("identical historical values: investigate temporal selection")
    result = dict(status="raw_raster_acquisition_QA_passed", epochs=records,
        common_valid_cells=int(valid.sum()), changed_cells=changes,
        masks_identical=all(np.array_equal(m, masks[0]) for m in masks),
        geographic_scope="bounding rectangle enclosing original project AOI; not polygon-clipped",
        bounds_5070=[-273195, 679455, -213075, 746835],
        source="https://dmsdata.cr.usgs.gov/geoserver/mrlc_Land-Cover-Native_conus_year_data/wcs",
        request=dict(service="WCS", version="1.0.0", request="GetCoverage",
            coverage="mrlc_Land-Cover-Native_conus_year_data:Land-Cover-Native_conus_year_data",
            bbox="-273195,679455,-213075,746835", crs="EPSG:5070", resx=30, resy=30,
            format="GeoTIFF", time="YEAR-01-01T00:00:00.000Z"),
        collection="MRLC advertises current Annual NLCD C1.2; this unversioned service response does not independently attest collection. Pin hashes; confirm version metadata before scientific release.",
        validation_status="No San Antonio model fitted, tuned, or validated here. 2025 remains held out.")
    (output / "qa.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "REPORT.md").write_text(
        "# San Antonio Annual NLCD acquisition test\n\n"
        "Result: PASS for raw raster acquisition and structural QA; scientific hindcast NOT run.\n\n"
        "Downloaded requested epochs 2005, 2015 and 2025 from the same official USGS service using WCS 1.0. "
        "Each has one categorical band, nominal 30 m cells (verified within 1e-6 m serialization tolerance), EPSG:5070 and the same grid. "
        "Historical arrays differ; this rules out the simple failure of returning identical maps for every year, "
        "but does not independently prove year provenance. Full class histograms, tags, input hashes and requests are in qa.json.\n\n"
        f"Common valid cells: {int(valid.sum()):,}. Changed cells: {json.dumps(changes)}.\n\n"
        "Earlier retry outcomes: anonymous requester-pays S3 listing and ScienceBase web access were denied; "
        "legacy MRLC WCS did not advertise annual land-cover epochs. The Annual NLCD WCS 2.0 request "
        "returned an XML server exception despite HTTP 200 (startTime null); its misleading .tif filename "
        "is retained as failed-response evidence, NOT accepted as raster input. WCS 1.0 succeeded. No AWS charges incurred.\n\n"
        "QA retry: the first checker rejected exact floating-point resolution equality. Inspection showed valid "
        "NLCD codes and pixel sizes 29.9999999848 × 30.0000001061 m. The checker now uses an explicit 1e-6 m "
        "tolerance; it does not resample or silently repair rasters. The initial empty qa directory is retained.\n\n"
        "Limitations: the extent is the original-project AOI bounding box, not its exact polygon; no source inputs "
        "were replaced. The bounds used an offline coordinate transformation, and polygon/edge QA remains. "
        "The service is unversioned and its TIFF tags do not independently establish Collection 1.2; retrieve "
        "corresponding collection metadata before release. NLCD is a classified reference, not error-free land use.\n\n"
        "Next: inspect/dissolve the original AOI, freeze version metadata, prepare time-valid drivers, specify "
        "class crosswalk/demand baselines and temporal/spatial validation protocol before fitting 2005→2015. "
        "Do not tune against 2025. This report does not establish 2050 predictive accuracy.\n")
    print(json.dumps({"status": result["status"], "changed_cells": changes, "common_valid_cells": int(valid.sum())}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs=3, required=True, metavar="RASTER")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report(args.inputs, args.output)
