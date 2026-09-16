# PLUS Production Workflow

**Audience:** Research, spatial-modeling, and engineering teams
**Status:** Approved architecture; runnable San Antonio engineering handoff/demo implemented; real PLUS runner and calibrated projections remain behind Phase 0 gates
**Use this for:** Producing future land-use baselines with PLUS and coupling them to Ecosystem Explorer, Urban InVEST, and health/equity analysis
**Do not use this for:** Current dashboard behavior (→ `ARCHITECTURE.md`), metric definitions (→ `../../REFERENCE.md`), or the rationale for choosing PLUS (→ `DESIGN_NOTES.md` §11.1)
**Source of truth for:** The proposed PLUS production workflow, its interfaces, validation gates, provenance, and resume behavior

---

## 1. Decision and boundary

PLUS is the selected **production land-change simulation engine** for the future-baseline branch of Ecosystem Explorer. This decision uses two forms of evidence:

- The model authors describe PLUS as a raster cellular-automata model combining the Land Expansion Analysis Strategy (LEAS) with multi-type Random Patch Seeds (CARS), designed to learn expansion drivers and reproduce patch dynamics.
- The project lead has direct confirmation from the PLUS lead author that PLUS is open source. Record this as **personal communication** until the repository or a release bundle provides the applicable license text and source-build instructions.

PLUS answers: **where is land conversion plausible under a stated future demand and set of transition rules?** It does not answer: **where should the city invest to maximize benefits?** The production system therefore keeps two branches separate:

1. **Predictive branch — PLUS:** produces business-as-usual and policy-constrained future background LULC.
2. **Normative branch — Explorer placement now, ROOT later if warranted:** places deliberate interventions such as green infrastructure or targeted tree canopy.

Both branches produce scenario rasters that are evaluated by the same Urban InVEST and health/equity pipeline. A PLUS probability is never interpreted as a social priority, and an optimized intervention is never described as a forecast.

### Decision summary

| Decision | Selected approach | Reason |
|---|---|---|
| Production simulator | PLUS | Strong urban-growth fit, nonlinear driver learning, and patch-forming allocation |
| First engineering pilot | San Antonio, conditional on Phase 0 data audit | Richest current ownership, scenario, compound-LULC, and five-model InVEST integration |
| Execution boundary | Out-of-process adapter | Decouples PLUS build/runtime details from the Streamlit app and permits repeatable batch execution |
| Initial operating mode | Offline, analyst-reviewed runs | Land-change calibration and validation are not suitable for live slider execution |
| First model role | Future baseline / counterfactual | Preserves the distinction between predicted change and planned intervention |
| Downstream evaluator | Canonical InVEST bundle plus the validated Explorer engine | Maintains the existing validation and handoff contract |
| Optimization | Keep current Explorer placement; evaluate ROOT later | ROOT optimizes activities and constraints but is not a land-change forecast |
| Comparison model | CLUE in the pilot only | Measures structural uncertainty without creating a second production dependency |
| LCM | Optional independent desktop check | Useful analyst workflow, but closed-source and Windows-bound |

---

## 2. End-to-end workflow

```text
Observed LULC t0, t1, t2 + time-valid drivers
                       │
                       ▼
        Harmonize grid, classes, nodata, and extent
                       │
                       ▼
       Derive transitions and train PLUS LEAS rules
                       │
                       ▼
   Hindcast t2 from information available at t1 only
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
      Validation gate       Failure diagnosis
            │               data / demand / allocation
            ▼
 Future demand + policy constraints + seed ensemble
                       │
                       ▼
              PLUS future LULC rasters
                       │
                       ▼
       Canonical scenario adapter and QC manifest
                       │
       ┌───────────────┴────────────────┐
       ▼                                ▼
Model-specific LULC views      Planner intervention branch
UFR / UCM / UNA / Carbon       Explorer now; ROOT later
       │                                │
       └───────────────┬────────────────┘
                       ▼
          Full Urban InVEST evaluation
                       │
                       ▼
     Health, exposure, access, and equity analysis
                       │
                       ▼
     Reviewed scenario release + comparison artifact
```

Every arrow is an explicit artifact handoff. No stage reads undocumented state from a GUI session.

---

## 3. Scenario taxonomy

Every production result must declare one and only one scenario role.

| Role | Meaning | Examples | Permitted claim |
|---|---|---|---|
| `observed` | Remotely sensed or authoritative historical LULC | 2011, 2016, 2021 maps | Observed subject to source accuracy |
| `plus_hindcast` | Simulation of a year for which an observed map exists | Simulated 2021 | Model-validation result |
| `plus_bau` | Future continuation of defined drivers/demand | 2030 BAU | Conditional projection, not prediction certainty |
| `plus_policy` | Future background under a policy constraint | Compact growth, protected land | Conditional policy scenario |
| `planner_intervention` | Deliberately placed action | Vulnerability-targeted trees | Normative intervention scenario |
| `combined` | Intervention applied to a named PLUS background | Targeted trees on 2030 BAU | Conditional combined scenario |

Required display language:

- Use **“PLUS conditional projection”**, never “expected future” or “forecast” without qualification.
- Use **“planner intervention”** for suitability- or optimization-driven placement.
- For `combined`, name both parents: for example, “Targeted canopy intervention on PLUS 2030 compact-growth background.”
- Never compare a future scenario with the present baseline without separating background land change from intervention effect.

The preferred factorial comparison is:

| Background | No intervention | Intervention |
|---|---:|---:|
| Present/observed | A | B |
| PLUS future | C | D |

This supports three estimands:

- Background change: `C − A`
- Intervention under current conditions: `B − A`
- Intervention under future conditions: `D − C`

Do not substitute `D − A` for any of these; it mixes background change and intervention effect.

---

## 4. Stable integration contract

The adapter, not PLUS-native files, is the boundary consumed by the rest of the project. The adapter accepts a run manifest and produces a validated scenario package.

### 4.1 Input manifest

The production contract below remains the target for calibrated releases. The runnable v1 engineering handoff (§16) validates grid/classes/transitions/demand and records artifact hashes, but does not yet authorize production releases or implement the complete calibration registry. Its manifest explicitly records these limits.

```json
{
  "schema_version": 1,
  "run_id": "<city>_<scenario>_<target_year>_<seed>",
  "engine": {
    "name": "PLUS",
    "version": "<release-or-commit>",
    "source_commit": "<commit-sha>",
    "build_id": "<container-or-runner-id>",
    "license_evidence": "personal-communication-pending-repository-artifact"
  },
  "geography": {
    "city_key": "<configured-city>",
    "crs": "<projected-crs>",
    "resolution_m": 30,
    "class_schema_id": "<versioned-planning-class-schema>",
    "reference_grid": "<path-or-content-id>",
    "aoi": "<path-or-content-id>"
  },
  "calibration": {
    "lulc_t0": "<path-or-content-id>",
    "lulc_t1": "<path-or-content-id>",
    "driver_manifest": "<path-or-content-id>"
  },
  "scenario": {
    "role": "plus_bau",
    "name": "<human-readable-name>",
    "target_year": 2030,
    "demand_table": "<path-or-content-id>",
    "transition_matrix": "<path-or-content-id>",
    "neighborhood_weights": "<path-or-content-id>",
    "restricted_areas": "<path-or-content-id>",
    "random_seed": 42
  }
}
```

The example values are illustrative. City, years, grid resolution, seeds, and scenario names are configuration, not global defaults.

### 4.2 Required output package

```text
run_id/
├── manifest.json                 exact inputs, parameters, hashes, runtime
├── plus_native/                  untouched PLUS outputs and logs
├── canonical/
│   ├── lulc_future.tif           canonical project taxonomy
│   ├── lulc_change.tif           from-class → to-class transition encoding
│   ├── transition_counts.csv     cells and area by transition
│   └── qc.json                   machine-readable validation results
├── invest/
│   ├── ufr_lulc.tif
│   ├── ucm_lulc.tif
│   ├── una_lulc.tif
│   ├── carbon_lulc.tif
│   └── crosswalk_audit.csv
└── review/
    ├── map_overview.png
    ├── change_map.png
    ├── patch_metrics.csv
    └── reviewer_decision.json
```

Rules:

- `plus_native/` is immutable evidence. Translation never overwrites it.
- All rasters match the declared reference grid exactly: CRS, transform, dimensions, resolution, and extent.
- `canonical/lulc_future.tif` is the only PLUS raster downstream components may consume directly.
- Model-specific rasters are generated from explicit crosswalks; no downstream model guesses a class meaning from its integer value.
- Every file in the package is hashed in `manifest.json`.

---

## 5. Data preparation

### 5.1 Observed LULC

Use at least three comparable epochs:

- `t0 → t1` for transition learning and allocation calibration.
- `t1 → t2` for a genuinely held-out hindcast.

All epochs must come from a harmonized classification. If source products or mapping methods changed, build and document a crosswalk and quantify the apparent transitions created by classification change. A visually cleaner recent product must not be mixed with an older product if the resulting “change” mainly reflects different mapping methods.

### 5.2 Drivers

Candidate drivers may include:

- distance to roads, transit, employment centers, and existing development;
- slope, water, floodplain, or other physical limitations;
- zoning and planned infrastructure;
- population and accessibility variables;
- parcel or ownership characteristics where legally and temporally appropriate.

Each driver record must include source, vintage, units, transformation, expected direction, missing-data treatment, license, and whether it was knowable at the hindcast cutoff. Drivers created after `t1` cannot be used to simulate `t2`.

Spatial cross-validation is mandatory when screening driver importance. Random cell splits overstate performance because neighboring pixels share landscape context.

### 5.3 Demand

PLUS allocates land quantities; it should not silently invent the policy narrative. Demand is supplied externally and versioned separately from spatial allocation.

For each future year and scenario, record:

- total area by LULC class;
- source model or planning document;
- demographic/economic/climate assumptions;
- protected or minimum-area targets;
- rounding and cell-balance reconciliation;
- low, central, and high demand variants where uncertainty is material.

Demand uncertainty and allocation uncertainty are separate ensemble dimensions. Do not collapse them into one set of random seeds.

### 5.4 Transition and neighborhood rules

Transition matrices are policy-bearing inputs. Every prohibited or allowed transition needs a reason, owner, and review date. Examples include preventing conversion of water or protected habitat, constraining redevelopment, or allowing only certain urban intensification pathways.

Neighborhood weights control patch growth and therefore influence cooling, access, and fragmentation outcomes. Estimate them from observed expansion as an initial value, then test sensitivity rather than tuning solely for the highest whole-map agreement.

### 5.5 Modeling taxonomy

Do not ask PLUS to learn thousands of compound NLCD × land-use × tree-canopy codes. That would fragment the training signal and turn small classification differences into apparent land transitions. PLUS should operate on a compact, mutually exclusive set of planning classes approved for the pilot—for example, low/medium/high-intensity developed land and a limited set of natural or agricultural classes.

After simulation:

- unchanged pixels retain their original compound attributes;
- changed pixels receive a target compound class only through a reviewed transition crosswalk;
- tree-canopy expansion that represents a deliberate intervention stays in the intervention branch unless it is an explicit land-change class in the observed training data;
- no conversion is assigned a default compound code merely because its intended combination is missing;
- every aggregation from source LULC to PLUS planning class and every expansion back to model-specific class is included in `crosswalk_audit.csv`.

This prevents the simulator from learning the downstream model encoding rather than the underlying land-change process.

---

## 6. Calibration and hindcast gate

### 6.1 Required comparisons

Evaluate the PLUS hindcast against:

1. the observed `t2` map;
2. a persistence/no-change baseline;
3. a quantity-correct random allocation baseline;
4. CLUE using the same demand and, as far as possible, the same transition constraints.

The comparison isolates four questions:

- Was the quantity of each transition correct?
- Was the location of change correct?
- Was landscape pattern reproduced?
- Were the important ecosystem-service and exposure consequences reproduced?

### 6.2 Metrics

Whole-map accuracy and Kappa may be reported but cannot determine acceptance. Required metrics are:

- transition-specific Figure of Merit;
- quantity disagreement and allocation disagreement;
- class-wise precision, recall, and area error for changed classes;
- multi-resolution or fuzzy agreement;
- patch count, patch-size distribution, edge density, compactness, and fragmentation;
- change allocation inside versus outside observed growth zones;
- hard constraint violations;
- downstream differences in UCM, UFR, UNA, Carbon, and UMH outputs.

Run multiple seeds and report the distribution, not only the best seed. The seed used for a published map must be predeclared or selected by a documented rule; choosing the best-looking realization after inspection is not allowed.

### 6.3 Proposed go/no-go criteria

These are project thresholds proposed for the pilot, not claims about PLUS generally:

- Zero prohibited transitions and zero changed cells outside the valid AOI.
- Exact reconciliation to demand within one raster cell per class after documented rounding.
- Transition-specific skill exceeds both persistence and quantity-correct random allocation.
- Patch metrics fall within a predeclared tolerance band derived from observed `t1 → t2` change.
- No material conclusion about the preferred intervention reverses solely because one favorable PLUS seed was chosen.
- The translated raster has 100% coverage in every required InVEST crosswalk, excluding declared nodata.
- Every canonical InVEST bundle executes without input-validation errors.

Numerical performance thresholds for Figure of Merit and patch metrics must be set after the Phase 0 data audit but before viewing the held-out `t2` result.

If PLUS does not clear the gate, diagnose quantity, suitability, transition rules, and allocation separately. Do not tune against downstream InVEST benefits or the target-year map until it “looks right.”

---

## 7. Production scenario ensemble

After the hindcast gate passes, production runs vary three independent dimensions:

1. **Demand:** low / central / high growth, or locally approved alternatives.
2. **Policy:** BAU / compact growth / protected-land or other named constraints.
3. **Allocation stochasticity:** a predeclared seed set.

The minimum useful design is not one map per narrative. It is an ensemble that permits reporting:

- per-pixel transition probability;
- stable versus seed-sensitive growth areas;
- class-area uncertainty;
- variation in patch morphology;
- variation in Urban InVEST and health/equity outcomes.

Publish one representative realization only alongside ensemble summaries. The representative-map selection rule—such as medoid realization in a declared metric space—must be chosen before reviewing policy outcomes.

---

## 8. Coupling PLUS to Urban InVEST

### 8.1 Translation sequence

1. Validate the raw PLUS output grid and class domain.
2. Translate PLUS classes into the canonical project taxonomy.
3. Create model-specific LULC views from versioned crosswalks.
4. Assert that every live pixel has a valid biophysical-table row.
5. Export the complete canonical InVEST bundle.
6. Execute canonical InVEST for release candidates.
7. Use the fast Explorer engine for interactive comparison only after parity checks cover the translated scenario class combinations.

The San Antonio compound LULC issue is the governing warning: a code valid for the flood table can mean something entirely different in a compound UCM, UNA, or Carbon table. Integer equality is not semantic compatibility.

### 8.2 Intervention overlay

For a future-background analysis:

1. Run PLUS to generate the background LULC.
2. Recompute eligibility on that future map; do not reuse the present-day convertible mask blindly.
3. Apply the planner intervention using the current Explorer placement logic or a later ROOT portfolio.
4. Produce both “future without intervention” and “future with intervention” rasters.
5. Run all downstream models on both rasters with identical non-LULC assumptions unless the scenario explicitly changes them.

This pairing yields the intervention estimand `future_with − future_without`. It prevents background urbanization from being misattributed to the intervention.

### 8.3 ROOT decision

ROOT remains a promising optional second-stage optimizer for parcel- or project-level activities, budget constraints, and agreement maps. It is not placed in the critical path for the first PLUS production release because:

- the current Explorer already supplies intervention placement and full-raster evaluation;
- ROOT requires activity-specific impact rasters and spatial decision units;
- UCM, UNA, and UMH have spatial interactions that violate a simple additive-benefit assumption;
- every ROOT shortlist would still require complete InVEST reruns.

Revisit ROOT after the PLUS future-background branch is validated and there is a concrete need for budget-constrained spatial portfolios.

---

## 9. Health and equity analysis

Keep health outcomes central and ecosystem-service indicators as mechanisms or co-benefits.

For each future background and intervention pair, report:

- population-weighted heat exposure and temperature change;
- preventable mental-health cases and avoided costs;
- urban-nature access and population below the demand threshold;
- children's nature access and access at schools where supported;
- benefit incidence by vulnerability dimension;
- high-vulnerability/low-benefit populations;
- absolute benefits and distributional shares.

Use matched-area or matched-canopy comparisons when testing placement strategies. If two scenarios change different amounts of land, separate the quantity effect from the placement effect. Preserve the established project estimand for any manuscript comparison; do not silently substitute citywide, pixel-weighted, or borough-weighted summaries for one another.

---

## 10. Reproducibility and provenance

Every released run records:

- PLUS version, source commit, build instructions, compiler, dependencies, and runtime image or runner;
- license identifier and license-file hash once available;
- input and output content hashes;
- LULC sources, vintages, classification crosswalks, and accuracy information;
- driver sources, vintages, transformations, and leakage audit;
- demand source and scenario narrative;
- transition matrix, neighborhood weights, random seed, and all model parameters;
- CRS, transform, extent, resolution, nodata, and resampling methods;
- adapter and downstream project commits;
- InVEST version and model arguments;
- validation metrics, reviewer, review date, and release decision.

Observed data, model-derived inputs, assumptions, and policy choices must be separately labeled in both the manifest and human-readable report.

### Licensing evidence

The project lead's personal communication is sufficient to correct the earlier statement that PLUS was not open source. It is not sufficient by itself for third-party redistribution or automated deployment because it does not specify the license obligations. Phase 0 therefore obtains one of:

- a repository `LICENSE` file with an identifiable license;
- a release archive containing the license;
- written permission specifying use, modification, redistribution, and publication terms.

This is a packaging gate, not a scientific-use veto. Research evaluation can proceed while the artifact is being obtained, provided the code and binaries are not redistributed beyond the confirmed permission.

---

## 11. Failure, restart, and audit behavior

Each phase writes a completion record and may resume only from an artifact whose hashes still match its manifest.

| Failure | Required response |
|---|---|
| Misaligned raster | Stop; regenerate from the reference grid; never resample categorical outputs silently downstream |
| Unknown LULC code | Stop before InVEST; add and review an explicit crosswalk |
| Demand mismatch | Stop; report per-class residual and correct the demand/allocation setup |
| Prohibited transition | Reject the run; do not mask the violation after simulation |
| Missing PLUS log or parameters | Mark run non-reproducible; do not release |
| One failed seed | Preserve the failed run and error; rerun only that seed after the cause is fixed |
| Hindcast gate failure | Return to data/demand/allocation diagnosis; do not advance to future claims |
| InVEST execution failure | Keep PLUS output intact; repair only the adapter or downstream bundle |
| Full InVEST reverses a screening result | Use full InVEST as authoritative and document the screening error |

Partial outputs are never promoted to the canonical scenario directory. Failed and superseded runs remain identifiable by `run_id` but are excluded from released comparisons.

---

## 12. Implementation plan and acceptance criteria

### Phase 0 — source, build, and data audit

**Owner:** spatial-model lead + engineer  
**Output:** build note, license artifact status, one tutorial run, candidate-city data audit  
**Acceptance:** source builds or a controlled runner executes; parameters and logs can be captured; a headless or automatable path is confirmed; three comparable LULC epochs exist.

**Preferred pilot:** San Antonio, because the current repository has the deepest ownership/eligibility data, NatCap reference scenarios, compound land-cover handling, and five-model InVEST export. This selection remains conditional: if three methodologically comparable historical LULC epochs and time-valid drivers cannot be assembled without classification artifacts, Phase 0 must evaluate Minneapolis before proceeding. The pilot choice is an engineering/data-readiness decision, not a claim that San Antonio is scientifically representative of all sustainable-cities applications.

The execution decision is made here:

- Prefer a reproducible headless build or command-line entry point.
- If only GUI execution is currently stable, use a controlled Windows runner for the pilot and export complete native configuration files and logs.
- Do not automate mouse clicks as the production interface.
- Do not reimplement LEAS/CARS until the authors' source and supported interfaces have been audited.

### Phase 1 — canonical adapter and preflight

**Owner:** engineer  
**Output:** manifest validator, grid/class preflight, immutable native-output capture, canonical LULC translator  
**Acceptance:** deliberately corrupted CRS, dimensions, nodata, class, transition, and demand fixtures all fail loudly; valid tutorial output packages reproducibly.

### Phase 2 — hindcast and structural comparison

**Owner:** spatial-model lead  
**Output:** PLUS hindcast ensemble, persistence/random baselines, CLUE comparison, validation report  
**Acceptance:** all §6 gates pass or the workflow stops with a documented diagnosis.

### Phase 3 — future background scenarios

**Owner:** scenario lead + stakeholders  
**Output:** approved demand/policy matrix, PLUS ensemble, representative-map rule, review maps  
**Acceptance:** assumptions approved; ensemble complete; no post-hoc scenario or seed selection.

### Phase 4 — InVEST and health coupling

**Owner:** ecosystem-service + health leads  
**Output:** model-specific LULC views, canonical InVEST runs, future-with/without intervention comparisons  
**Acceptance:** 100% crosswalk coverage; canonical models execute; estimands and aggregation units match the intended comparison.

### Phase 5 — Explorer integration

**Owner:** application engineer  
**Output:** new PLUS provenance type, scenario selector, audit panel, downloadable manifest/bundle  
**Acceptance:** PLUS scenarios are visibly labeled conditional projections; current scenario outputs and 40/40 regression baselines remain unchanged; all new provenance and subset assertions pass.

---

## 13. Explicit postponements

The first production increment does **not** include:

- live PLUS execution inside Streamlit;
- pixel-by-pixel ROOT optimization;
- automatic selection of a “best” future scenario;
- joint fitting of land change to maximize InVEST benefits;
- unreviewed translation of new PLUS classes into compound InVEST codes;
- claims that one future realization is the forecast;
- model tuning against the same target map used for final validation;
- scaling to multiple cities before one city passes the complete workflow.

These postponements keep the first implementation auditable and prevent the predictive, normative, and ecosystem-service layers from contaminating one another.

---

## 14. Decision log

| Decision | Status | Evidence / trigger | Revisit when |
|---|---|---|---|
| Select PLUS as production future-LULC engine | Approved | Author-described LEAS+CARS design; project-lead confirmation of open-source status | Hindcast fails or supported execution cannot be made reproducible |
| Prefer San Antonio for the first engineering pilot | Conditional approval | Strongest existing scenario, ownership, compound-LULC, and InVEST integration | Phase 0 cannot establish three comparable historical epochs and time-valid drivers |
| Record open-source status as personal communication for now | Approved | Direct communication reported by project lead | Repository/release license artifact arrives |
| Run PLUS outside the interactive app | Approved | Batch calibration, native runtime, and reproducibility needs | A supported, deterministic library API becomes available |
| Keep current placement engine for interventions | Approved | Existing InVEST-derived priorities and full-raster evaluation | Budget-constrained spatial optimization becomes a funded requirement |
| Keep ROOT out of first critical path | Approved | Different model role and non-additivity concerns | PLUS branch passes and portfolio optimization is requested |
| Use CLUE only as a pilot comparator | Approved | Structural-uncertainty value without duplicate production maintenance | PLUS hindcast is unstable or CLUE materially outperforms it |
| Exclude LCM from core pipeline | Approved | Closed source, Windows dependency, weak deployment fit | A partner requires LCM replication or an interoperable service emerges |

---

## 15. Primary references

- PLUS repository and model description: <https://github.com/HPSCIL/Patch-generating_Land_Use_Simulation_Model>
- Liang et al. (2021), PLUS method: <https://doi.org/10.1016/j.compenvurbsys.2020.101569>
- CLUE model family and downloads: <https://www.environmentalgeography.nl/site/data-models/data/clue-model/>
- TerrSet Land Change Modeler: <https://www.clarku.edu/geospatial-analytics/terrset-liberagis-features/land-change-modeler/>
- ROOT workflow: <https://natcap.github.io/ROOT/rst/workflow.html>
- InVEST documentation: <https://storage.googleapis.com/releases.naturalcapitalproject.org/invest-userguide/latest/en/index.html>

Personal communication evidence: the project lead reports direct confirmation from the PLUS lead author that PLUS is open source. Date and correspondence identifier should be added to the run registry when available; do not place private correspondence in the public repository without permission.

---

## 16. Runnable San Antonio demo and handoff

### 16.1 What is implemented

`plus_workflow.py` and `scripts/run_plus_workflow.py` implement an offline, additive workflow. They do not change dashboard equations, the scenario-return contract, or `SCENARIO_SCHEMA_VERSION`. The demo is runnable with the project dependencies in `requirements.txt`:

```bash
python scripts/run_plus_workflow.py audit
python scripts/run_plus_workflow.py demo --output outputs/plus_san_antonio_demo
python scripts/run_plus_workflow.py verify --run outputs/plus_san_antonio_demo
```

Use a **new output directory** for every run. Existing directories are never overwritten. A failed run has no completed `manifest.json`; retain its files for diagnosis and restart in a new directory. Run products are ignored by git (`outputs/plus_*/`); the code and source record are tracked. The completed example on 2026-09-16 is `outputs/plus_san_antonio_demo_v3/review/report.html`.

The executable chain is:

1. Audit configured San Antonio model inputs and hash them.
2. Derive a 16-class, one-based NLCD planning raster from the compound baseline. Preserve the original compound source untouched.
3. Produce explicit class/compound assumptions, restriction raster, allowed-transition edge list, demand template, and historical/engine-record templates.
4. Import an external PLUS result **or**, in `demo` mode, generate a deterministic growth stress fixture. The latter is distance-to-developed allocation with seed noise; it implements neither LEAS nor CARS and carries engine name `engineering_fixture`.
5. Reject unknown classes, CRS/grid drift, nodata changes, prohibited transitions, restricted conversions and, for imported PLUS runs, demand-count mismatches.
6. Preserve unchanged compound NLUD/canopy attributes; expand changed planning classes using an explicit representative-class table. These representatives are **unreviewed scenario assumptions**, not recovered future canopy observations.
7. Place the same food-forest footprint on both current and background maps.
8. Reuse the existing Explorer UCM/UNA/UFR/Carbon/UMH functions. Evaluate full-extent HMI and fixed-population-weighted HMI separately. MH contrasts use the explicit paired exposure baseline because the response is nonlinear.
9. Estimate intervention-only food capacity from the four report crop benchmarks, without claiming citywide net agricultural production.
10. Write scenario and contrast CSVs, raster views, patch checks, maps, HTML report, four canonical InVEST input bundles, review decision and hashed manifest. Verify saved artifact integrity after completion.

This is a **complete engineering demo from current city inputs to evaluated artifacts**. It is not a completed PLUS calibration, independent canonical-model execution or scientifically validated future forecast. Production release is always `false` in v1, even if approval flags are edited in an imported engine record.

### 16.2 Test experiment and decisions

| Component | Demo choice | Justification / boundary |
|---|---|---|
| Geography | Existing San Antonio/Bexar modeled extent, EPSG:5070, 30 m | Reuse the current equal-area model grid; not a city-boundary reproduction |
| Background | 2,000 grass/shrub/pasture/crop cells become developed low intensity (180 ha) | Stress-test the adapter and downstream sensitivity; not estimated growth demand |
| Intervention | 1,000 cells (90 ha), food forest | Exercise compound conversion and food/co-benefits together |
| Placement | Current HMI-ranked, existing convertible developed cells, public ownership classes 1–4; fixed footprint in both backgrounds | Reuse available masks; isolate the background effect from changing intervention location |
| External constraints | Water, snow/ice and wetlands preserved; only declared transitions allowed | Conservative engineering checks; no claim of approved zoning rules |
| Food | Report Table A2-4 per-crop discounted yields, equal shares, mature benchmark | Auditable source-derived capacity; no use of the app's unverified SA scalar |
| Evaluation | Existing model-aligned functions plus canonical input bundles | Fast, consistent demo without duplicating equations; independent canonical execution is still a separate step |
| Deployment | Offline CLI, no dashboard integration or background upload | Keep calibration work out of live app reruns and avoid changing established UI behavior |

The intervention screen differs from the 2023 project's underutilized-land, ownership and parcel-size filters. In particular, raster public ownership classes 1–4 do not reproduce utility ownership or military/airport exclusions; a 1-acre parcel minimum is not enforced. The demo therefore does not select authoritative project-eligible parcels. The project replication path needs the original parcel/eligibility mask, city boundary and scenario-specific compound views. Do not infer exact parcel eligibility from 30 m cells.

No establishment trajectory is modeled: `--food-establishment-fraction` scales only the food benchmark (0–1); canopy/cooling/carbon retain the selected compound conversion classes, including source canopy tiers preserved by the existing conversion lookup. Mature food productivity and biophysical vegetation growth are not jointly calibrated. `--skip-bundles` is available for rapid engineering runs but omits the canonical handoff files.

### 16.3 Source review from the supplied San Antonio materials

- Public report: [Vibrant Land (2023)](https://naturalcapitalproject.stanford.edu/sites/default/files/publications/report_-_san_antonio_urban_agriculture_-_2023_final_standard.pdf), pp. 48–53. The crop table was visually checked; provenance and numeric transcription are in `data/sa/food_forest_yield_report_2023.json`.
- Live [model-input readme](https://docs.google.com/document/d/1514Wlu6woL7XUJyeMDsynA7Oh-kBbqrkzST3e2D67Go/edit): read-only text export retrieved on 2026-09-16, SHA256 `a7ba048799da726e65120f414ab7ee7fb311868d84ef63e880f52eb9e841034d`. Its UCM factors/weights/distances, UNA demand/radius/decay and flood rainfall match the selected bundle parameters. Local curated files are reused, not re-downloaded wholesale.
- [August 2024 data folder](https://drive.google.com/drive/u/1/folders/1FxlHVWFfICc5j-f7z9sWUBrVJj1Lw1zQ) and [crop-model slides](https://docs.google.com/presentation/d/1mLv2fxWPcZOuGOanTHHwfHrIojY8bC8nHh6b9Z-1dRk/edit): links recorded; their full live contents were not inspected because no Drive/Slides connection is available. Do not claim the local corpus is a complete mirror or that the slide model has been reproduced.

Food source discrepancy: the narrative reports approximately 11,483 lb/acre/year, while Table A2-4's discounted quarter-acre values are mulberry 1,500, pecan 188, fig 2,250 and nopal 7,500. Their sum is **11,438**, a difference of 45. The demo uses the explicit table sum and flags reconciliation for the team. The commercial-production discount is already included, and the quarter-acre units already represent each crop's equal share of one acre: neither discounting nor division by four should be repeated. This is a mature, uniform-productivity benchmark. It is not observed food production, complete household nutrition, or total background crop production; crop-production losses from the growth fixture are not estimated. The existing app's SA yield scalar (8,500) is left unchanged pending a separate reviewed output-change decision.

### 16.4 Running real PLUS instead of the fixture

```bash
python scripts/run_plus_workflow.py prepare --output outputs/plus_sa_preparation
```

Provide three comparable epochs and time-valid drivers using the generated historical manifest as a checklist. Use the author-supported source build/runner (preferred) or a controlled Windows analyst environment. The official [PLUS repository](https://github.com/HPSCIL/Patch-generating_Land_Use_Simulation_Model) currently documents Windows execution and ships a `.exe`; no verified headless entry point is configured here. Open-source status is accepted from the author's communication; source access/build support is still a practical deployment prerequisite. We do not synthesize an unsupported command line or substitute another CA model under the PLUS name.

The generated CSVs are **project contracts**, not claimed PLUS-native parameter-file formats. Translate them into the version-specific PLUS UI/configuration and archive those exact native settings. Train LEAS on t0→t1, then run CARS for held-out t2. Remap all epochs/output to the declared one-based planning schema and exact reference grid. Retain full native outputs and logs. Evaluate the hindcast before assembling future demand and policy scenarios.

```bash
python scripts/run_plus_workflow.py hindcast \
  --current /absolute/path/to/t1_planning.tif \
  --observed /absolute/path/to/t2_observed_planning.tif \
  --simulated /absolute/path/to/t2_plus_planning.tif \
  --output outputs/plus_sa_hindcast_metrics.json
```

This calculates changed-cell FoM, quantity/allocation disagreement, class precision/recall, persistence and three quantity-correct random comparators. Optional `--restricted` constrains the random comparator; `--clue-raster` adds an independently produced CLUE comparison. No-change FoM is `null`, not a vacuous perfect score. This command is a diagnostic component, not the complete approval gate: transition-specific FoM, spatially blocked analysis, patch similarity, seed ensembles and downstream error still require §6's review.

For future import, fill a copy of `inputs/engine_record.template.json`. Required fields include PLUS version, source/binary SHA256, runner, license-evidence identifier, role, target year, seed, and actual parameter/log/demand file paths. Relative evidence paths resolve against the record's directory. Demand CSV uses `planning_class,target_cells` and must match output class totals exactly. The schema and expansion representatives must match the preparation package; expansion requires analyst review. Native raster/logs/settings/demand are copied into `plus_native/` without modifying their source files.

```bash
python scripts/run_plus_workflow.py import \
  --plus-raster /absolute/path/to/plus_future_planning.tif \
  --engine-record /absolute/path/to/engine_record.json \
  --output outputs/plus_sa_2030_review
python scripts/run_plus_workflow.py verify --run outputs/plus_sa_2030_review
```

Import validates artifact consistency; it cannot establish that the external settings/logs constitute an authentic, well-calibrated run. A completed import stays `external-plus-import-review-pending`, and v1 cannot authorize production use. Manual analyst review of provenance, hindcast and constraints is mandatory.

### 16.5 Acceptance and reproducibility

Fast tests:

```bash
python -m unittest discover -s tests -p test_plus_workflow.py -v
python verify_baselines.py
```

The contract tests include rejected CRS/grid drift, nodata changes, unknown classes, protected conversions, prohibited transitions, missing compound crosswalks, demand mismatch, template engine records, altered artifacts, random-comparator quantities, food units/discounting and deterministic fixture allocation. Full-city demo acceptance requires four evaluated scenarios, identical eligible intervention footprints, zero prohibited/restricted conversions, correct transition areas, manifest hashes and all canonical bundles. The integrity receipt and manifest itself are excluded from the manifest's artifact hash inventory to avoid self-reference.

Runtime tested on 2026-09-16: `snapp` environment (Python 3.11; NumPy 2.4.6; SciPy 1.17.1), with scikit-image 0.26.0, lazy-loader 0.5, imageio 2.37.4 and tifffile 2026.3.3 installed into `/tmp/ecosystem-explorer-demo-deps` only. No existing environment was rewritten. Because this host's environment differs from the project requirements, use the established project environment for normal reproduction; the temporary verification invocation was:

```bash
PYTHONPATH=/tmp/ecosystem-explorer-demo-deps \
MPLCONFIGDIR=/tmp/ecosystem-explorer-mpl-cache \
XDG_CACHE_HOME=/tmp/ecosystem-explorer-cache \
conda run -n snapp python scripts/run_plus_workflow.py demo \
  --output outputs/plus_san_antonio_demo_v3
```

### 16.6 Remaining gates and requests to the research team

1. Obtain the PLUS source/build or controlled runner from the lead author; capture exact version, binary/source hash, native settings and seed behavior. No outbound request is sent automatically.
2. Supply or approve a comparable three-epoch LULC series and historically valid drivers. The August 2024 curated compound map is a current-condition evaluator input, not three historical epochs.
3. Approve future class quantities, transition rules and protection masks; demand is currently illustrative.
4. Supply the original report eligibility/parcels/city boundary if reproducing urban-agriculture project scenarios, including utility ownership and military/airport exclusions.
5. Reconcile the food-table/narrative discrepancy and review NLUD/canopy expansion assumptions.
6. Execute independent canonical InVEST runs, validate hindcasts and ensembles, and add defensible heat-health/equity parameters before decision use. Heat-related mortality, irrigation demand, nutrient export and urban-farm scenarios are not included in v1.

The independent canonical smoke executions for all four demo scenarios are now completed (§16.7–16.8); this remaining gate applies to calibrated release-specific scenarios and scientific validation, not to rerunning the same demo just to obtain an execution receipt.

### 16.7 Independent canonical execution and smoke comparison

An optional separate runner executes the exported bundle in an InVEST environment, never in the app's environment. It checks archive paths/symlinks and size before extraction, uses absolute resolved input paths, writes fresh per-model workspaces, and records failures or completion. The engineering manifest is not rewritten or promoted by these sidecar results.

```bash
conda run -n urban-cooling-invest-3.20.2 python \
  scripts/run_canonical_plus_bundle.py \
  --bundle outputs/plus_san_antonio_demo_v3/invest/D_background_food_forest/canonical_invest_bundle.zip \
  --output outputs/plus_sa_canonical_D_v1
python scripts/compare_plus_canonical.py \
  --demo outputs/plus_san_antonio_demo_v3 \
  --canonical outputs/plus_sa_canonical_D_v1 \
  --scenario D_background_food_forest
```

Use another fresh directory for each scenario or rerun. Default execution includes UCM, UFR, Carbon, UNA and UMH depression/anxiety (six executions across five model families); `--models` selects a subset. The smoke comparator requires all six and is verified for **InVEST 3.20.2 only**. It confirms the bundle hash, compares HMI cellwise, flood/access/carbon aggregates and MH native-grid totals, and exits nonzero on disagreement. This adds scenario-specific smoke evidence without changing the existing 3.19.0 baseline parity registry or dashboard badges.

Two engineering lessons from the live run:

- Canonical Carbon's `c_change_bas_alt` is **t C/ha** per its installed model specification. Sum density × 0.09 ha/cell × 44/12 to obtain t CO2; directly summing the raster creates an apparent 11.11-fold mismatch. The comparator includes a unit test for this integration. No model equation was changed.
- Canonical UMH outputs have a padded native grid (1,733 × 2,004 versus the 1,713 × 1,984 input grid). The comparison sums native case events with an explicit edge/padding caveat rather than resampling counts or claiming cellwise parity. These are synthetic exposure/prevalence case-event proxies, not measured health outcomes.

UNA emitted a NumPy overflow warning during execution; the run completed. Finite, masked output comparisons are checked, and the warning is not treated as empirical validation. The smoke thresholds are HMI MAE ≤1e-4, UFR mean difference ≤1e-4 (including rounded storm/index parameters), UNA share difference ≤0.01 percentage points, Carbon relative tolerance 1e-4 / absolute 0.2 t CO2, and MH native-total tolerance 2% / absolute 0.2 events. Baseline zero-delta matches alone are vacuous; the nonzero B/C/D scenario comparisons provide the useful guards.

### 16.8 Recorded demo results (engineering assumptions only)

The test uses 2,000 background-conversion cells (180 ha) and the same 1,000 intervention cells (90 ha) in B and D. No prohibited/restricted conversions or nodata changes occurred; food-forest compound fallback counts are zero. The artifact-integrity check covers 54 files, excluding the self-referential manifest and verification receipt. All 21 contract tests, all 40 dashboard baselines and associated assertions, all 24 canonical executions and all four input-matched smoke comparisons passed. The demo ran before its implementation commit: the manifest records the base git commit plus exact source-file hashes; those hashes identify the evaluated code rather than implying a clean checkout at run time.

| Contrast | Area-mean HMI delta | Nature access delta (percentage points) | Carbon stock delta (t CO2) | Intervention food capacity (lb/year) | Paired MH proxy events |
|---|---:|---:|---:|---:|---:|
| Background C−A | −0.000087589 | −0.003876 | −11,066.7 | 0 (background crop production not assessed) | −25.0 |
| Current intervention B−A | +0.000208139 | +0.081612 | +33,016.4 | 2,543,752 | +36.4 |
| Future intervention D−C | +0.000208139 | +0.081619 | +33,016.4 | 2,543,752 | +36.4 |

These tiny full-extent HMI deltas do not describe cooling at the planted cells or constitute observed site temperature changes. The nearly identical intervention contrasts reflect this particular fixed footprint/background fixture, not general robustness to urban growth. The food total is mature benchmark capacity on 90 ha of assumed productive food forest, not assured yield or food-security impact. The crop fraction parameter must not be interpreted as an establishment trajectory for the other models.

Canonical sidecars are stored separately as `outputs/plus_sa_canonical_A_v1/` through `...D_v1/`; each contains `execution_receipt.json`, resolved args, workspaces, native logs and `smoke_comparison.json`. For D, HMI MAE is 8.98e-9; canonical paired carbon is 33,016.425 t CO2 versus Explorer 33,016.4, and paired MH proxy events are 36.416 versus 36.4. The code and docs preserve production release as `false` despite these computational checks. Final test/receipt status should be read directly from the saved artifacts rather than inferred from this narrative.

### 16.9 San Antonio 2050 scope and source-access audit (2026-09-16)

**User-confirmed scope:** target year 2050; San Antonio AOI; offer food forests, tree canopy, urban agriculture and combinations. Growth may be adopted-plan-informed or exploratory, subject to further consensus. Historical US NLCD is approved as the candidate land-cover validation source. This updates the research scope, not the existing engineering fixture or its release status.

**Subsequent user decisions (same date):** compare both growth backgrounds; show several intervention area and budget levels; use the original project AOI after inspecting its geometry. Accordingly, the ten central alternatives below are the starting matrix, to be expanded into separate area-constrained and budget-constrained experiments, not a single fixed intervention size. Area and monetary levels are not yet specified. Preserve the original AOI source and inspect extent, geometry validity, CRS, overlap with project rasters and city limits before declaring an exact reporting polygon.

**Preliminary local AOI inspection:** `data/sa/natcap_2024/acs_block_groups_3857.gpkg` has one layer, 1,124 valid/nonempty/non-null Polygon features in EPSG:3857. County identifiers are Texas/Bexar (`48/029`, 1,118 features), Comal (`48/091`, 3) and Guadalupe (`48/187`, 3). WGS84 bounds are approximately `[-98.80656, 29.16666, -98.20459, 29.76071]`. This is a project block-group collection, not proven to equal municipal limits or the final project reporting footprint. An online PROJ datum-grid lookup failed because `cdn.proj.org` could not resolve in the sandbox; an explicit offline transform produced finite EPSG:5070 coordinates. No area from the failed online transform is accepted. Exact transformation resources, dissolved geometry, overlap/coverage, source-folder equivalence and the final AOI checksum still require review.

**Verified source access:**

- The [PLUS repository](https://github.com/HPSCIL/Patch-generating_Land_Use_Simulation_Model) recursive tree at `de7ba6efd35b530da6c37e81103276a17716602c` was inspected with `truncated=false`. It contains `PLUS V1.4.2.exe`, runtime resources, test data and English tutorials. No C/C++ source/header, common build-project or license file was found in that tree. This does not negate the author's open-source confirmation; it identifies the limits of this particular distribution.
- The executable was downloaded locally to ignored `outputs/plus_2050_source_audit/PLUS_V1.4.2.exe`; size 78,532,096 bytes; SHA256 `2f49f4f01c0a209d0d67fabef9013d41fca30b1632e334898abadad5c2eb25d4`. File inspection identifies a PE32+ Windows x86-64 GUI executable. It has not been executed or redistributed. `wine`, `prlctl` and `VBoxManage` were not found on PATH; this is not a complete inventory of available Windows infrastructure.
- The user-linked [input README](https://docs.google.com/document/d/1514Wlu6woL7XUJyeMDsynA7Oh-kBbqrkzST3e2D67Go/edit) exported successfully; SHA256 `a7ba048799da726e65120f414ab7ee7fb311868d84ef63e880f52eb9e841034d`. It names `acs_block_group.gpkg` for cooling/nature-access AOI and council districts for flood AOI. These are not automatically the same boundary. Exact polygon selection and a boundary checksum remain necessary.
- The user-linked [data folder](https://drive.google.com/drive/u/1/folders/1FxlHVWFfICc5j-f7z9sWUBrVJj1Lw1zQ) redirected to Google account sign-in in the available in-app browser. No folder listing or new raster downloads were obtained. Existing local NatCap inputs remain usable but are not a verified complete mirror of the shared folder. No account login or sharing change was attempted.
- [USGS Annual NLCD](https://www.usgs.gov/centers/eros/science/about-annual-nlcd) reports Collection 1.2 through 2025, annually back to 1985. The [official access page](https://www.usgs.gov/centers/eros/science/annual-nlcd-data-access) provides several distribution routes and identifies AWS access as requester-pays. An anonymous S3 listing probe for the C1.2 mosaic prefix returned HTTP 403; no historical rasters were downloaded. Do not treat map-service renderings as categorical analysis rasters or silently incur requester-pays charges.

**Design with confirmed choices and remaining methodological review:**

1. Use a single Annual NLCD collection/version for all epochs at native 30 m resolution. Candidate equal-duration split: 2005→2015 for LEAS fitting/tuning, 2015→2025 for final held-out hindcast. Reserve 2025 from tuning; use earlier temporal folds and spatial blocks. After evaluation is locked, refit for 2050 projections using available historical data. Pin actual downloaded versions and metadata, inspect confidence/change products and persistent versus transient transitions, and document any source classification error. NLCD is reference land cover, not error-free observed land use or independent validation of ecosystem services. The existing app/compound overlay uses legacy NLCD 2021, not Annual NLCD C1.2. Do not mix those sources as historical epochs or silently overwrite the current baseline; quantify their overlap-year disagreement and reconcile the compound baseline separately before 2050 evaluation.
2. Produce two conditional 2050 backgrounds: historical-trend exploratory and plan-informed. [SA Tomorrow](https://www.sa.gov/Directory/Departments/Planning/SA-Tomorrow) was adopted in 2016 and presents growth expectations to 2040. Its county-level totals must not be assigned directly to the city AOI; extension to 2050 and conversion of population/housing/jobs to land demand need explicit assumptions, density constraints and sensitivity ranges. Call the latter **plan-informed research scenario**, not an adopted 2050 forecast.
3. Cross each background with five alternatives: no intervention, food forest only, tree canopy only, urban agriculture only, and a mixed portfolio. This yields ten central scenarios before demand/seed/parameter ensembles. Compare each intervention with its own no-intervention background. Where feasible, hold land area or cost constant across alternatives and report both; resolve the comparison basis before optimization. Mixed portfolios need non-overlapping decision units or explicit co-location rules to prevent double counting.
4. Keep canopy as a separate fractional attribute where planting does not change developed land cover; do not convert every tree-planted developed cell into forest. Keep food forest and annual agriculture distinct in yields, vegetation structure, irrigation, carbon pools, runoff and nature-access assumptions. Review new intervention crosswalks/parameters before implementation; the existing food-forest fixture is not evidence that all four alternatives are implemented.
5. Use the confirmed AOI as the reporting/intervention boundary. Test a surrounding modeling buffer for spatial context and edge effects, with growth demand calculated for the simulation domain and reported separately for the AOI. Exact AOI, buffer and demand-allocation rules remain decisions; do not substitute the rectangular raster extent for the city polygon.
6. Maintain separate experiments for land-cover effects under fixed climate/population and joint 2050 climate/population assumptions. Holding current ET, temperatures, storm and population fixed isolates land-cover effects but does not create a complete 2050 health or climate forecast. Historical drivers must be dated to the prediction origin; current road/ownership layers must not leak into a claimed historical hindcast.

**Immediate decisions/access needed:** inspect and identify the exact original-project polygon; intervention eligibility (public/vacant versus broader land); actual area and budget levels, currency/price year, establishment and maintenance horizon; accessible Drive session or equivalent local folder; a compatible Windows runtime for the available PLUS binary. Data acquisition and preparation can proceed independently of the final intervention budget. Native PLUS reproduction, held-out validation and reviewed demand/crosswalks remain mandatory before replacing `engineering_fixture` or claiming production readiness.
