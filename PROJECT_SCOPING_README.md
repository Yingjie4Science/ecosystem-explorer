# Ecosystem Explorer: Project Scoping Review

**Purpose:** Meeting guide for deciding what Ecosystem Explorer should become, what the next bounded phase should deliver, and what should wait.

**Prepared for:** Project-owner discussion with the engineer

**Current assessment:** The repository is a strong exploratory prototype with a credible modeling core and unusually careful documentation. Its next challenge is not adding capability. It is choosing a narrower user, decision, and evidence standard so that the product tells one coherent and defensible story.

---

## Executive summary

The recommended center of gravity is:

> **Ecosystem Explorer is a scenario pre-screening and handoff tool that helps an urban-planning or research team compare a small set of land-use alternatives, understand their modeled tradeoffs and limitations, and send selected candidates to canonical InVEST and human review.**

It should not currently be positioned as a final decision engine, a citywide impact forecast, or an optimizer that determines the best intervention. Its strongest value is shortening the path from a planning question to a transparent, reviewable set of candidate scenarios.

For the next phase:

- Make **San Antonio the flagship use case**, because it has the richest spatial targeting, ownership, NatCap reference, and export workflow.
- Keep **Minneapolis as a methodological and regression reference**, not a second equally complete product promise.
- Build the product story around one end-to-end workflow: **define the planning question → set constraints → compare candidate scenarios → inspect who and where benefits → export a candidate → validate in canonical InVEST → review with stakeholders**.
- Default to the few outcomes that are sufficiently interpretable for the selected decision. Treat weakly calibrated health, food, cost, and monetized impacts as optional research modules rather than equal headline evidence.
- Invest the next phase in clarity, validation coverage, and a successful real-user walkthrough before adding cities, models, or optimization features.

---

## 1. The most important scope decision

The meeting should settle one question before discussing features:

> **What real decision should this tool help a specific person make?**

The current prototype can serve several audiences, but these are different products:

| Possible primary user | Decision they need to make | Product implication |
|---|---|---|
| City planner or program manager | Which candidate areas and intervention mixes merit further study? | Simple constraints, maps, distributional results, implementation context, and a short comparison report matter most. |
| NatCap/InVEST modeler | Which exploratory scenarios should be promoted into canonical model runs? | Provenance, parameter visibility, reproducible exports, and validation comparisons matter most. |
| Research team | Which hypotheses or scenario designs deserve formal analysis? | Reproducible methods, sensitivity analysis, uncertainty, and stable estimands matter most. |
| Public-facing stakeholder | What might different greening strategies change? | A much smaller metric set, plain language, and strong guardrails against interpreting modeled scenarios as forecasts are required. |

**Recommendation:** Design the next phase primarily for the first two users: a planning/research team working with an InVEST-capable analyst. Do not try to serve the general public or automate final decisions yet.

---

## 2. Recommended product definition

### What the product should do

1. Start with a concrete planning question, such as where a city should investigate green-infrastructure investment under geographic or ownership constraints.
2. Let the user define a bounded scenario rather than an unconstrained abstract mix.
3. Show a small set of understandable outcomes, their spatial distribution, and the population or area represented.
4. Make assumptions, proxies, model coverage, and scenario provenance visible at the point of interpretation.
5. Compare a manageable set of alternatives against a clearly defined baseline.
6. Export the selected candidate and its complete assumptions for canonical InVEST execution and expert review.
7. Preserve a scenario record so the same comparison can be reproduced later.

### What it should not promise

- It does not select the objectively best intervention.
- It does not establish causal health effects or predict observed future outcomes.
- It does not replace canonical InVEST, engineering studies, parcel/title review, budgeting, or stakeholder deliberation.
- It does not make metrics comparable merely because they appear together on one dashboard.
- It does not turn placeholder costs, synthetic inputs, or broad benchmark rates into local evidence.

---

## 3. Recommended flagship workflow

Use **San Antonio** for the primary demonstration and product-development path:

1. Select one council district or another clearly named planning area.
2. Apply an implementation constraint, such as a public/vacant-land planning screen.
3. Compare three to five scenarios, including the baseline and a small number of intelligible intervention strategies.
4. Review cooling, runoff retention, nature access, carbon storage, and distributional effects using clearly stated scopes and denominators.
5. Inspect the spatial placement and eligibility funnel.
6. Select one or two candidates for further analysis.
7. Export them to canonical InVEST with a complete scenario and limitation record.
8. Record the canonical results and reviewer decision outside the exploratory layer, or re-import them in a later phase if that becomes a demonstrated need.

Minneapolis remains valuable as:

- an independent city configuration for detecting hard-coded assumptions;
- a regression and model-method test case;
- a future second product workflow after the San Antonio use case succeeds with real users.

---

## 4. Which outcomes should lead

The dashboard currently gives many outcomes similar visual weight. For a scoped product, the default view should reflect the decision rather than the number of available models.

### Recommended default evidence

- **Cooling:** Lead with the modeled heat-mitigation quantity and a carefully qualified temperature translation.
- **Flood:** Lead with runoff retention or another canonical per-pixel quantity; clearly separate it from simplified citywide indices and dollar proxies.
- **Nature access:** Keep the denominator and modelable extent visible; include distribution across neighborhoods or relevant populations.
- **Carbon:** Use the San Antonio four-pool stock framework, explicitly labeled as a one-time stock change.
- **Feasibility:** Show eligible and converted area, spatial constraints, and user-supplied implementation assumptions.

### Keep optional or secondary for now

- **Mental-health cases and avoided costs:** The calculation may reproduce the model algorithm, but synthetic NDVI and uniform national prevalence do not support a local health-impact claim. Keep this as a research module until better exposure and baseline-health inputs are available.
- **Food production:** Treat as an illustrative benchmark until locally appropriate crop or food-forest yield data and management assumptions exist.
- **Implementation and cost-effectiveness values:** Use only when local cost components and the benefit denominator are appropriate for the intended decision. Do not let default placeholder costs appear decision-ready.
- **Cooling-energy and flood-damage dollars:** Keep subordinate to the biophysical outcomes until building coverage and valuation scope support local totals.

---

## 5. Lessons to carry over from the urban-cooling-health work

The largest analytical risk is not a wrong equation; it is answering a different question with a reasonable-looking number.

Every reported result should therefore identify:

- the baseline and comparison scenario;
- geographic scope;
- population or land denominator;
- aggregation rule, including whether it is a raster mean, population-weighted measure, regional mean, sum, or point sample;
- temporal basis, especially annual flow versus one-time stock;
- physical units and any conversion;
- currency and price year for monetary quantities;
- observed inputs, modeled inputs, proxies, and assumptions;
- uncertainty or validation boundary;
- whether the number is generated by the Explorer, displayed from NatCap, predicted by a surrogate, or produced by canonical InVEST.

The same definition should travel with the result into the interface, downloaded comparison, export bundle, report, and manuscript. A label or tooltip alone is not enough if downstream artifacts can silently change the estimand.

---

## 6. What success should mean for the next phase

The next phase should be accepted only when all of the following are true:

- A named primary user can complete the flagship San Antonio workflow without developer guidance.
- The user can explain what decision the tool supports and what it does not decide.
- Every default metric has an explicit scope, denominator, temporal basis, provenance, and permitted interpretation.
- A selected scenario can be reproduced from its saved record.
- The exported candidate runs in the agreed canonical InVEST version.
- Explorer and canonical outputs are compared using the same scenario, extent, inputs, units, and aggregation rule.
- The interface prevents predicted, proxy, displayed, and canonical results from being mistaken for one another.
- At least one real planning or research walkthrough produces a documented decision: advance, revise, or reject a candidate scenario.
- Known missing data and assumptions remain visible rather than being filled with convenient defaults.

User satisfaction, number of metrics, and number of available cities are not sufficient acceptance criteria on their own.

---

## 7. Questions to settle with the engineer

### Product and audience

1. Who is the primary user for the next phase?
2. What decision should they make differently or faster after using the tool?
3. Is the intended deliverable a meeting demonstration, a research instrument, or an operational planning workflow?
4. Is San Antonio acceptable as the single flagship use case for the next phase?

### Workflow

5. What exact starting information does the user have?
6. Which constraints must they be able to express?
7. How many scenarios should a normal session compare?
8. What is the required handoff after exploration: downloadable report, InVEST bundle, GIS layer, or analyst review?
9. Who reviews and approves a scenario before it is used externally?

### Evidence and validation

10. Which three to five outcomes are required for the flagship decision?
11. For each outcome, what is the required evidence level: exploratory direction, model-method parity, local calibration, or observed validation?
12. Which comparison grain controls: citywide, district, neighborhood, population-weighted, or parcel-constrained?
13. What canonical InVEST runs must be reproduced before a result can be shown as validated?
14. Which assumptions should users be allowed to change, and which should be governed project settings?

### Delivery and capacity

15. What is the engineer's available time and the target date for the next reviewable milestone?
16. What work requires a modeling scientist, GIS/data owner, health expert, or planner rather than software engineering?
17. Which current features can be hidden or postponed to protect the flagship workflow?

---

## 8. Recommended phased scope

### Phase A — Agree on the product contract

- Name the primary user and decision.
- Confirm San Antonio and one flagship planning question.
- Select the default outcome set.
- Define the evidence and validation threshold for each outcome.
- Define the required final handoff and reviewer.

**Exit condition:** A one-page scope statement describes the user, decision, workflow, outputs, exclusions, evidence standards, and acceptance criteria.

### Phase B — Make one workflow trustworthy and easy to use

- Simplify the interface around the flagship path.
- Make scenario scope, provenance, denominators, and limitations persistent.
- Demonstrate reproducible scenario save and export.
- Run the agreed canonical comparisons.
- Conduct a walkthrough with at least one intended user.

**Exit condition:** The user completes the workflow and produces a reviewable candidate without developer interpretation.

### Phase C — Evaluate whether to broaden

- Review what users actually used, misunderstood, or ignored.
- Decide whether the next investment should improve inputs, add an outcome, add a city, or support canonical-result re-import.
- Expand only when the flagship workflow has demonstrated value and the additional feature changes a real decision.

**Exit condition:** A documented go/no-go decision identifies the next bounded use case and the evidence required for it.

---

## 9. Explicitly postpone

Unless tomorrow's meeting identifies a specific decision that requires them, postpone:

- additional cities;
- additional ecosystem-service models such as NDR;
- claims of global or pixel-level optimization;
- mortality or other new health-impact models;
- AlphaEarth or other new imagery pipelines;
- parcel editing and freehand drawing;
- authentication, multi-user workflow, and production backend work;
- public-facing deployment beyond a controlled prototype audience;
- further visual polish that does not remove a demonstrated usability barrier.

---

## 10. To-do list

### Before or during the scoping meeting

- [ ] Agree on the primary user.
- [ ] Write the one-sentence decision the tool supports.
- [ ] Confirm or reject San Antonio as the flagship use case.
- [ ] Select one flagship planning question and example geography.
- [ ] Choose the three to five default outcomes.
- [ ] Agree on which current outcomes should be secondary or hidden.
- [ ] Define the final handoff and the person or role responsible for review.
- [ ] Agree on the evidence threshold for each default outcome.
- [ ] Identify the engineer's time constraint and next reviewable milestone.
- [ ] Record explicit exclusions for the next phase.

### Immediately after scope agreement

- [ ] Create a one-page product and evidence contract.
- [ ] Create a metric-definition register covering scope, denominator, aggregation, temporal basis, units, provenance, assumptions, and permitted interpretation.
- [ ] Map the existing interface to the flagship workflow and identify screens or controls to hide.
- [ ] Define two or three representative acceptance scenarios.
- [ ] Identify missing inputs and assign each to software, modeling, GIS/data, health, or planning expertise.
- [ ] Define the canonical-InVEST comparison matrix required for acceptance.
- [ ] Schedule one real-user walkthrough before broader development.

### Deferred technical improvement backlog

These are important, but they should follow the product-scope decisions above rather than drive tomorrow's meeting.

- [ ] Pin a reproducible runtime environment rather than relying only on open-ended minimum package versions.
- [ ] Add automated verification for the established regression gate.
- [ ] Break the very large application and verification files into bounded modules and focused test suites.
- [ ] Make the metric-definition register machine-readable and reuse it across the interface, downloads, exports, and documentation.
- [ ] Expand canonical parity checks from baseline cases to representative intervention scenarios and city/model combinations.
- [ ] Separate algorithm parity, input calibration, and decision fitness in the validation presentation.
- [ ] Add a software license and a data-source/license manifest.
- [ ] Update validation setup instructions so a new contributor can reproduce the environment without relying on machine-specific environment names or paths.
- [ ] Add a controlled record for valuation constants, currency, price year, discounting, and update rules.
- [ ] Reduce duplicated or stale documentation after the product contract becomes authoritative.

---

## Recommended opening for the meeting

> The prototype already demonstrates substantial capability. I do not want the next phase to be defined by adding more features. I want us to agree on the primary user, the specific decision this tool supports, the flagship San Antonio workflow, and the evidence standard for each result. Then we can define one bounded milestone that takes a user from a planning question to a transparent candidate scenario and a canonical InVEST handoff.

