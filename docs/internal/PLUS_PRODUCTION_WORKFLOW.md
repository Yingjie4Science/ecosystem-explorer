# PLUS Production Workflow

**Audience:** Research, spatial-modeling, and engineering teams
**Status:** Approved architecture; implementation staged behind Phase 0 gates
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

The repository will eventually validate this contract in code. Until that implementation lands, every field below is mandatory in the run record.

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
