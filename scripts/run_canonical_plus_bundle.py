#!/usr/bin/env python3
"""Execute a PLUS-handoff bundle in a separate canonical-InVEST environment.

The execution receipt never promotes a fixture to a calibrated PLUS release.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
from pathlib import Path
import stat
import time
import zipfile

MODELS = {
    "cooling": ("urban_cooling_model", "urban_cooling_args.json"),
    "flood": ("urban_flood_risk_mitigation", "urban_flood_risk_mitigation_args.json"),
    "carbon": ("carbon", "carbon_args.json"),
    "nature": ("urban_nature_access", "urban_nature_access_args.json"),
    "mh_depression": ("urban_mental_health", "urban_mental_health_depression_args.json"),
    "mh_anxiety": ("urban_mental_health", "urban_mental_health_anxiety_args.json"),
}


def extract_checked(bundle, output):
    output = Path(output).resolve()
    with zipfile.ZipFile(bundle) as archive:
        if sum(info.file_size for info in archive.infolist()) > 1024 ** 3:
            raise ValueError("Bundle uncompressed size exceeds 1 GiB limit")
        for info in archive.infolist():
            target = (output / info.filename).resolve()
            if not target.is_relative_to(output) or Path(info.filename).is_absolute() or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError(f"Unsafe archive member: {info.filename}")
        archive.extractall(output)


def resolved_args(args, package, workspace):
    out = dict(args)
    out["workspace_dir"] = str(workspace)
    for key, value in out.items():
        if isinstance(value, str) and value.startswith(("inputs/", "./inputs/")):
            path = (package / value).resolve()
            if not path.is_relative_to(package) or not path.is_file():
                raise ValueError(f"Missing/unsafe input for {key}: {value}")
            out[key] = str(path)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", nargs="+", choices=tuple(MODELS), default=list(MODELS))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    package = output / "bundle"
    extract_checked(args.bundle, package)
    logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(output / "canonical_execution.log")])
    import natcap.invest
    receipt = {"invest_version": natcap.invest.__version__,
               "bundle_sha256": hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
               "production_release_allowed": False, "models": {},
               "scope": "Canonical execution smoke test; not empirical or hindcast validation"}
    receipt_path = output / "execution_receipt.json"
    for name in args.models:
        module_name, args_name = MODELS[name]
        config = json.loads((package / "args/prototype_grid" / args_name).read_text())
        config = resolved_args(config, package, output / f"workspace_{name}")
        (output / f"{name}_resolved_args.json").write_text(json.dumps(config, indent=2))
        started = time.monotonic()
        print(f"Running canonical InVEST {natcap.invest.__version__}: {name}", flush=True)
        try:
            module = importlib.import_module("natcap.invest." + module_name)
            module.execute(config)
            receipt["models"][name] = {"status": "completed", "elapsed_seconds": time.monotonic() - started}
        except Exception as error:
            receipt["models"][name] = {"status": "failed", "error": repr(error)}
            receipt_path.write_text(json.dumps(receipt, indent=2))
            raise
        receipt_path.write_text(json.dumps(receipt, indent=2))
    print(f"Canonical execution receipt: {receipt_path}", flush=True)


if __name__ == "__main__":
    main()
