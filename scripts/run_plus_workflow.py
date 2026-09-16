#!/usr/bin/env python3
"""See docs/internal/PLUS_PRODUCTION_WORKFLOW.md §16 for runnable examples."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import plus_workflow as workflow


def main():
    parser = argparse.ArgumentParser(description="Offline PLUS handoff; fixture demo is NOT a PLUS forecast")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("audit")
    verify = sub.add_parser("verify")
    verify.add_argument("--run", type=Path, required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--output", type=Path, required=True)
    for command in ("demo", "import"):
        run = sub.add_parser(command)
        run.add_argument("--output", type=Path, required=True)
        run.add_argument("--intervention-cells", type=int, default=1000)
        run.add_argument("--seed", type=int, default=42)
        run.add_argument("--skip-bundles", action="store_true")
        run.add_argument("--food-establishment-fraction", type=float, default=1.0)
        if command == "demo":
            run.add_argument("--growth-cells", type=int, default=2000)
        else:
            run.add_argument("--plus-raster", type=Path, required=True)
            run.add_argument("--engine-record", type=Path, required=True)
    hindcast = sub.add_parser("hindcast")
    for flag in ("current", "observed", "simulated"):
        hindcast.add_argument("--" + flag, type=Path, required=True)
    hindcast.add_argument("--output", type=Path, required=True)
    hindcast.add_argument("--clue-raster", type=Path)
    hindcast.add_argument("--restricted", type=Path)
    args = parser.parse_args()
    if args.command == "audit":
        print(json.dumps(workflow.audit(), indent=2))
    elif args.command == "verify":
        print(json.dumps(workflow.verify_run(args.run), indent=2))
    elif args.command == "prepare":
        workflow.prepare(args.output)
        print(f"Prepared {args.output}; real PLUS execution is external")
    elif args.command == "hindcast":
        current, profile = workflow.read_raster(args.current)
        observed, _ = workflow.read_raster(args.observed, reference=profile)
        simulated, _ = workflow.read_raster(args.simulated, reference=profile)
        metrics = workflow.hindcast_metrics(current, observed, simulated)
        metrics["persistence"] = workflow.hindcast_metrics(current, observed, current)
        restricted = None
        if args.restricted:
            restrictions, _ = workflow.read_raster(args.restricted, reference=profile)
            restricted = restrictions != 0
        metrics["quantity_correct_random"] = [workflow.hindcast_metrics(current, observed,
            workflow.quantity_correct_random(current, observed, seed, restricted)) for seed in (42, 43, 44)]
        if args.clue_raster:
            clue, _ = workflow.read_raster(args.clue_raster, reference=profile)
            metrics["clue"] = workflow.hindcast_metrics(current, observed, clue)
        metrics["release_approved"] = False
        workflow.write_json(args.output, metrics)
    else:
        workflow.run(args.output, native=getattr(args, "plus_raster", None),
                     engine_record=getattr(args, "engine_record", None),
                     growth_cells=getattr(args, "growth_cells", 2000),
                     intervention_cells=args.intervention_cells, seed=args.seed,
                     make_bundles=not args.skip_bundles,
                     food_establishment_fraction=args.food_establishment_fraction)


if __name__ == "__main__":
    main()
