# Credit Decision, Simulation & Optimisation Platform — Requirements

> **Document structure.** This document is in two parts.
>
> **Part A (Sections 0–15)** is the *decisioning engine* specification: data, rules, waterfall,
> risk model, provenance, simulation, optimisation. It is the intellectual core of the product and
> is unchanged in substance. Section numbers in Part A are referenced by the code and the test
> suite and **must not be renumbered**.
>
> **Part B (Sections 16–31)** is the *platform* specification, added 2026-09-19 after the commercial
> context changed: this is no longer a demo, it is a deliverable to a Saudi bank, deployed inside
> their estate, integrated with their data, used by multiple named users, and licensed commercially.
> Part B covers deployment, tenancy, identity, licensing, integration, configuration lifecycle,
> upgrades, open modelling, experimentation, monitoring, and the generalisation from
> "approval simulator" to "decision platform".
>
> **Where Part A and Part B conflict, Part B wins.** In particular, Part A Section 2 previously
> placed authentication, databases and deployment out of scope. They are now in scope; see
> Section 16 onward. Part A's engine contracts (Section 15) remain binding, extended by Section 29.

## 0. Instructions to the coding agent (read first)

- You are building **production software for a regulated bank**, not a demo. Favour correctness,
  clarity, explainability and auditability over sophistication. Nothing that produces a number a
  credit committee might act on may be approximate, unlabelled, or silently wrong. Every discipline
  Part A imposes on provenance and support exists precisely because the deployment target is real.
- **Scope is delivered in tranches, not all at once.** Read Section 17 before planning any work.
  Tranche 1 (the engine, Part A) is largely built. The platform requirements in Part B are a
  multi-month programme and must not be faked into a three-day sprint; Section 17 says exactly what
  ships when, and what the first client-facing milestone honestly contains.
- Work in the **phases in Section 11** (engine) and the **tranches in Section 17** (platform). After
  each phase or tranche: run tests, then **stop** and print a summary (files changed, test results,
  key numbers, open issues). Do not start the next one until told to.
- Do not invent requirements. If something is ambiguous, pick the simplest reasonable option, and list it under "Assumptions" in the phase summary.
- **Read Section 15 before writing any code.** The function and object signatures there are contracts between phases. Do not change them; if one is genuinely unworkable, stop and say so in the phase summary rather than silently redesigning it.
- Every performance number shown anywhere must carry a **provenance label**: `OBSERVED`, `PREDICTED`, `INFERRED` or `NOT_MODELLED` (see Section 6). Never present an inferred number as observed.
- **`true_bad` is forbidden outside `generate_data.py` and `validation.py`.** It must never be read, joined, or referenced by the loader, rule engine, risk model, simulator or optimiser. This is enforced by a test (Section 13).
- If the calibration targets in Section 5.3 cannot all be met, **adjust the generator distributions in 5.2 — never the strategy defaults in 7.1, and never the targets themselves.** Report exactly what you changed in the phase summary.
- Keep all business parameters in `config.yaml`. No magic numbers in code.
- Environment: Python 3.11+, virtualenv. Must run on Windows (Git Bash) and Ubuntu WSL. Use relative paths and `pathlib`.

## 1. Goal

Answer, for a lender: *"Given my current credit strategy and risk appetite, where can I change the strategy to approve more applicants without exceeding my bad-rate limit?"*

The prototype must:
1. Load a historical application population (approved + declined).
2. Reproduce the current approve/decline strategy, and account for every mismatch.
3. Show a decline waterfall.
4. Let the user change strategy parameters and simulate the impact on approval rate and bad rate.
5. Find a better strategy automatically, subject to a bad-rate constraint (default ≤ 3.5%).
6. Explain where the incremental approvals come from, and how much of the answer rests on inference rather than observation.

## 2. Scope boundaries of the engine (Part A)

These are the boundaries of the **engine specification in Part A only**. Several of them are lifted
by Part B; the column below says where.

| Boundary | Status |
|---|---|
| Expected loss, fraud-rate and profitability constraints | Not implemented in Part A. The constraint *framework* is general (Section 10.2.1); only `bad_rate` is implemented. Adding the others is a config entry plus one metric function — see Sections 10.2.1 and 29.3. |
| Pricing, credit limits, exposure | Not implemented in Part A. These become **domain packs** under Section 29; the engine must not assume a binary approve/decline action set. |
| Champion/Challenger execution | **Now in scope** — Section 27. Part A delivers the exported versioned strategy object (10.5); Part B runs traffic through it and measures actual versus expected. |
| Existing-book actions | **Now in scope as a domain pack** — Section 29. Not part of the first client milestone. |
| Authentication, databases, deployment | **Now in scope** — Sections 18, 20, 22, 31. |
| Multi-tenancy, RBAC, audit, licensing | **Now in scope** — Sections 19, 20, 21. |
| Reject inference beyond (a) a single multiplicative conservatism penalty and (b) the near-cutoff override anchor in Section 9.4 | Still out of scope. No parcelling, augmentation, or bivariate models. This is a deliberate honesty boundary, not a backlog item: the product's claim is that it *labels* what it does not know, and each additional inference technique adds a layer of unfalsifiable modelling on top of that claim. Revisit only with real bureau-performance data on declines (Section 25.4). |

## 3. Tech stack

- Python 3.11+, pandas, numpy, scikit-learn, pyyaml, pyarrow, streamlit, plotly, pytest.
- Store data as Parquet in `data/`.
- Pin versions in `requirements.txt`.

## 4. Project structure

```
origination-sim/
  config.yaml
  requirements.txt
  README.md
  data/                       # generated parquet (gitignored)
  src/
    contracts.py              # dataclasses from Section 15 — write this first
    generate_data.py          # synthetic data generator
    loader.py                 # load + validate schema
    rules.py                  # strategy definition + rule engine
    waterfall.py              # decline waterfall
    risk_model.py             # PD model, training support, provenance labelling
    segments.py               # segment definitions / banding
    simulate.py               # what-if simulation
    optimise.py               # greedy optimiser + naive comparison + swap-out analysis
    strategy_io.py            # versioned strategy export / import (JSON)
    validation.py             # synthetic-oracle checks — the ONLY module besides the
                              # generator allowed to touch true_bad
  app/
    streamlit_app.py          # entry point; one module per page under app/pages/
    pages/
  tests/
    conftest.py               # shared fixtures: cfg, sample, synthetic, model, strategy
    fixtures/sample.parquet   # ~500 rows, committed, used by most tests
    test_generator.py
    test_rules.py
    test_waterfall.py
    test_model_support.py
    test_simulate.py
    test_optimise.py
    test_leakage.py
```

## 5. Data

### 5.1 Schema (one row per application)

| Column | Type | Notes |
|---|---|---|
| application_id | str | unique |
| app_date | date | spread over 12 months |
| age | int | 19–65 |
| employment_type | category | `salaried`, `self_employed`, `other` |
| monthly_income | float | INR |
| loan_amount | float | INR, requested principal |
| tenor_months | int | 12–60 |
| existing_emi | float | INR/month |
| proposed_emi | float | INR/month, derived from loan_amount, tenor and a config APR |
| foir | float | (existing_emi + proposed_emi) / monthly_income |
| bureau_score | float, nullable | 300–900; null for no-hit |
| bureau_vintage_months | int | months of credit history |
| max_dpd_12m | int | one of 0, 30, 60, 90 |
| enquiries_6m | int | bureau enquiries in last 6 months |
| fraud_flag | bool | failed fraud/verification |
| hist_decision | category | `approve` / `decline` — historical decision **as actually taken** |
| hist_decline_reason | str, nullable | rule id of first failed rule, or `MANUAL_OVERRIDE` |
| manual_override | bool | the historical decision differs from the written strategy (Section 5.2.1) |
| booked | bool | = (hist_decision == approve) for this prototype |
| bad_flag | Int8, nullable | 1/0 for booked only (90+ DPD within 12 months); null for declines |
| true_bad | Int8 | **synthetic only**, outcome for every applicant. Used only by `validation.py`. Never for training, simulation or optimisation. |

`loan_amount` and `tenor_months` are not used by the prototype's rules or model. They are in the schema so that expected loss, pricing and limit strategies can be added later without regenerating data.

`loader.py` must validate this schema, so a real dataset with the same columns (minus `true_bad`) can replace the synthetic one later. If `true_bad` is absent, the Validation page is hidden.

**Performance-window assumption:** every booked application is treated as fully seasoned — 12 months of performance is assumed available for all of them, including the most recent cohort. Real data would need vintage-based censoring. State this assumption on the Overview page.

### 5.2 Synthetic generator

- 1,000,000 rows, fixed random seed from config. Must be reproducible.
- Distributions (starting points; tune to hit the targets in 5.3):
  - bureau_score ~ Normal(**720**, 60), clipped to 300–900. About 10% no-hit (null score) or bureau_vintage_months < 6.
  - age: draw so that roughly **5%** falls outside 21–60 (the rest spread over 21–60). Do not draw uniformly over 19–65 — that makes R1_AGE decline ~15% of the book and the approval-rate target unreachable.
  - employment_type: salaried 60%, self_employed 30%, other 10%.
  - monthly_income ~ lognormal, median ₹45,000.
  - loan_amount ~ lognormal, median ₹300,000, correlated with income; tenor_months in {12, 24, 36, 48, 60}. Derive proposed_emi from these at a config APR, then derive existing_emi so that foir has median about 0.40, right-skewed, max 1.2.
  - max_dpd_12m and enquiries_6m correlated with low score.
  - fraud_flag about 2%.
- True default probability for every applicant:
  `logit(p) = β0 + β1·(700 − score)/20 + β2·foir + β3·dpd_indicator + β4·enquiries_6m + β_emp`
  Salaried gets a negative (safer) effect; self_employed and other positive. Draw `true_bad ~ Bernoulli(p)`.
- Apply the current strategy (Section 7.1) to set the *written-strategy* decision, then apply manual overrides (5.2.1) to produce `hist_decision` and `hist_decline_reason`. Set `bad_flag = true_bad` where booked, null otherwise.

#### 5.2.1 Manual overrides (required — do not skip)

Real lenders override their own strategy at the margin. Model this:

- **1.0%** of applications get `manual_override = True`.
- **70%** of those are decline → approve flips, drawn **predominantly from bureau_score 650–699 and foir 0.50–0.60** (i.e. marginal cases), among applicants who pass all mandatory rules. Selection is **mildly favourable**: within the band, pick applicants with a lower true PD more often than chance (e.g. sample with weight inversely related to `p`).
- **30%** are approve → decline flips, scattered across the approved population, with `hist_decline_reason = 'MANUAL_OVERRIDE'`.

This exists for three reasons, all of which the rest of the spec depends on:
1. It makes the reproduction check in 7.3 non-vacuous.
2. It puts **real observed performance just below the cutoff**, which is the only honest anchor the prototype has for reject inference (Section 9.4).
3. The favourable selection is deliberate — it means override performance *understates* the band's true bad rate, which the UI must warn about.

### 5.3 Calibration targets (generator must hit these; print them after generation)

| Metric | Target |
|---|---|
| Baseline approval rate | 38–42% |
| Observed bad rate of approved | 2.5–3.2% |
| True bad rate, score 680–699, rules otherwise passed | 4–6% overall |
| True bad rate, score 680–699, salaried, FOIR ≤ 35% | 2.5–3.5% |
| Each decline rule in waterfall | ≥ 1% of applications |
| Reproduction match rate (7.3) | 98.8–99.2%, and **every** mismatch has `manual_override == True` |
| Booked rows with bureau_score in 650–699 | ≥ 5,000 |

Rows 3 and 4 ensure there is a real "hidden good" pocket for the optimiser to find, and that uniformly lowering the cutoff is worse than a targeted change. The last row ensures the near-cutoff inference anchor has enough data to be worth showing.

## 6. Provenance labels (mandatory)

| Label | Meaning |
|---|---|
| `OBSERVED` | Actual bad_flag of booked applicants |
| `PREDICTED` | Model PD for booked applicants — used for model fit checks and for the model-basis baseline (6.1) |
| `INFERRED` | Model PD for historically declined applicants × conservatism penalty |
| `NOT_MODELLED` | Applicant falls outside the model's training support (Section 9.2). **No PD is produced.** |

Every portfolio bad rate in simulation or optimisation is reported as:
- the **observed component** (retained booked customers),
- the **inferred component** (newly approved declines that have a PD),
- the **blended total**,
- and, separately, the **count and share of approvals that are `NOT_MODELLED`**.

`NOT_MODELLED` approvals are counted in the approval rate but are **excluded from the blended bad-rate numerator and denominator**. The UI must state this next to the figure — e.g. "blended bad rate 3.42% (excludes 12,400 approvals with no model support)". Never silently impute a PD of zero, and never let a `NOT_MODELLED` population be folded into a headline bad rate.

The UI must also show the share of the approved population whose performance is inferred.

### 6.1 Model-basis baseline (required)

Comparing an `OBSERVED` baseline bad rate against a blended observed+inferred scenario mixes a real strategy effect with model bias. So every simulation and optimisation result must also report a **model-basis baseline**: the mean `PREDICTED` PD of the baseline booked population, on the same modelling basis as the inferred component.

Show all three on screen: observed baseline, model-basis baseline, scenario blended. If observed and model-basis baselines differ materially, the model is biased and the scenario delta should be read with that in mind — say so in the UI.

## 7. Strategy and rule engine

### 7.1 Current strategy (in config, applied in this order; first failed rule = decline reason)

| ID | Rule | Default | Relaxable |
|---|---|---|---|
| R1_AGE | age between 21 and 60 | 21, 60 | No (mandatory) |
| R2_FRAUD | fraud_flag == False | — | No (mandatory) |
| R3_THIN_FILE | score not null and vintage ≥ 6 | 6 | Yes |
| R4_BUREAU_HIST | max_dpd_12m < 60 and enquiries_6m ≤ 6 | 60, 6 | Yes |
| R5_SCORE | bureau_score ≥ cutoff | 700 | Yes |
| R6_FOIR | foir ≤ cap | 0.50 | Yes |

### 7.2 Requirements

- Strategy is a data object (loaded from config, editable in UI), not hard-coded logic. See `Strategy` in Section 15.
- The engine returns for each application: decision, first failed rule, and **all** failed rules (boolean per rule).
- Support **segment overrides** — extra approve-rules produced by the optimiser, of the form "score in [a, b) AND foir ≤ x AND employment_type in {…} → approve". Semantics, which must be implemented exactly as written:
  1. Mandatory rules (R1_AGE, R2_FRAUD) are evaluated first and always. An applicant failing either can never be approved, by any path.
  2. Base rules are evaluated next.
  3. An override may only flip **decline → approve**. It can never turn an approval into a decline.
  4. An override applies only if the applicant satisfies the override's own conditions **and** passes every base rule the override does not explicitly relax.
  5. Overrides are evaluated after base rules; order between overrides is irrelevant because they can only add approvals.
- Support **segment exclusions** — the mirror image of an override, produced by the swap-out trade in 10.3, of the form "score in [a, b) AND foir in [x, y) AND employment_type in {…} → decline". Semantics, again exactly as written:
  1. An exclusion may only flip **approve → decline**. It never approves anyone.
  2. Exclusions are evaluated after the base rules and **before** overrides, and no override may relax an exclusion. An applicant the strategy excludes cannot be brought back by any override path.
  3. An excluded applicant's decline reason is the exclusion itself, not a base rule — they passed every base rule. The 8 waterfall needs a step for them.
  This is the only way the strategy object can express the swap-out trade. Without it, the trade's net figures cannot pass through `simulate()`, cannot be exported and cannot be validated. See 10.3.
- Mandatory rules can never be relaxed or overridden, by the UI or the optimiser.
- Editing a rule parameter that the rule does not have must **raise**, listing the valid names. A scenario is driven by hand-written JSON through the 11.1 CLI; a typo that is silently accepted runs as a no-op and reports "0 swap-ins, nothing changed", which reads exactly like a real finding.
- Vectorised pandas/numpy only. No row loops. Must evaluate 1M rows in under 2 seconds.

### 7.3 Reproduction check

Re-applying the current strategy to the loaded data must match `hist_decision` for every row **except manual overrides**. Report on the Overview page:
- the raw match rate (expected ~99.0%),
- the match rate excluding `manual_override == True` rows (must be **100%**),
- a table of the mismatches with their override direction.

If the second number is below 100%, the rule engine is wrong — fail loudly, do not round it away.

## 8. Waterfall

- Sequential waterfall: applications → removed by R1 → R2 → … → approved. Counts and % of total. Manual overrides are shown as a separate final adjustment step so the waterfall reconciles to the actual approved count.
- **Derive that step from the `manual_override` flag, never as a residual.** A step computed as "whatever is left over" makes the reconciliation vacuous: a genuine rule-engine bug is relabelled as a manual override and the waterfall still balances, telling a confident wrong story. Disagreement between the engine and history on a row that is *not* flagged must raise. The same rule applies to the scenario waterfall in 10.1.
- **Single-rule declines**: count of declines that failed exactly one rule, by rule. These are the near-miss opportunity.
- A **score band × FOIR band** heatmap of declined volumes.

## 9. Risk model

### 9.1 Training

- Train a logistic regression **on booked customers only** with target `bad_flag`. Fixed `random_state` from config.
- Features: bureau_score, foir, max_dpd_12m (one-hot), enquiries_6m, employment_type (one-hot).
- **Drop any categorical level with fewer than `min_level_obs` booked observations (config, default 100)** rather than fitting a coefficient to it. With the baseline strategy, `max_dpd_12m` levels 60 and 90 have no booked observations at all; a level with no data must not silently receive a coefficient of zero, because that makes the riskiest applicants score as safe.
- No-hit / thin-file applicants have no score: exclude them from the model and mark them `NOT_MODELLED`.
- 70/30 train/test split. Report AUC and a calibration table (predicted vs observed bad rate by decile) on the test set. AUC must be **≥ 0.60**; below that the pipeline is broken, not the data.
- Show coefficients in a table (explainability).

### 9.2 Training support (required)

The model must expose the region it is entitled to speak about. **Marginal support is not sufficient
on its own**, and checking only marginally will produce a confidently wrong demo. Every booked row
with `bureau_score < 700` in this dataset comes from the overrides in 5.2.1, whose FOIR is clustered
around 0.53. So a marginal check certifies "score 680–699" (thousands of booked rows, all at high
FOIR) and "FOIR ≤ 0.35" (tens of thousands of booked rows, all above the cutoff) separately, while
the **combination** of the two has almost no observations behind it. Both checks below are required.

**Marginal support — decides whether a PD is produced**

- Bin each numeric feature into deciles of the **full application** population. A bin is *supported* if it contains at least `min_support_obs` booked observations (config, default 200).
- **Dense is not the same as observed.** A bin can hold thousands of booked rows and still span values no booked customer has. On discrete features the decile edges collapse: `enquiries_6m` produces four bins, the top one spanning 3–23 with ~47,000 booked observations behind it, while no booked customer exceeds 6. Support therefore also requires the value to lie **within the min–max of the booked rows the model was fitted on**. Without this clause, relaxing `max_enquiries` to 12 produces ~1,400 approvals priced by linear extrapolation seventeen units beyond any training data, every one of them scored, none flagged `NOT_MODELLED`.
- A categorical level is supported if it survived the `min_level_obs` filter in 9.1.
- An applicant is `NOT_MODELLED` if **any** of its feature values falls in an unsupported bin or level, or if it has no bureau score.
- `RiskModel.predict_pd()` must return NaN — not a number — for `NOT_MODELLED` rows. Callers must handle them per Section 6.

**Joint support — decides how much that PD is worth**

- `RiskModel.cell_support(df)` returns, for each row, the number of booked training observations in that row's **segmentation cell** (the 10.2.2 dimensions; by default score band × FOIR band × employment_type).
- Joint support never changes a decision and never changes a PD. It is an **evidence count that travels with the number**, and it must appear wherever an inferred PD is aggregated: every segment row in the optimiser output, every swap-in breakdown row in the simulator.
- A cell holding fewer than `min_cell_obs` booked observations (config, add it; default 100) is labelled **THIN** beside its inferred bad rate.
- Do **not** suppress, exclude or down-weight THIN cells. The recommendation genuinely depends on them; the requirement is that the user can see what it rests on.

**Reporting**

- The Risk model page must display, per feature, the supported range or levels and the count of applications inside and outside it — **as counts, not merely a pass/fail flag.** Several bins sit within ~10% of the `min_support_obs` threshold, so a boolean alone conceals how close the classification is to flipping on a change of seed.
- It must also display a joint-support table: booked observations per segmentation cell, with the cells the optimiser is most likely to reach highlighted.
- Report separately the count of applications that sit in a *supported bin* but *outside the booked range*. That is the population the range clause is holding back, and it is invisible in a per-bin table. If the count is zero, the clause is inert and something upstream is wrong.

The marginal check is what stops the What-if page cheerfully approving 90-DPD applicants at a 3%
predicted bad rate. The joint check is what stops the optimiser recommending eighteen thousand
approvals in a cell backed by fifty observed customers without saying so.

### 9.3 Conservatism penalty and sensitivity

- INFERRED PD = model PD × `inference_penalty` (config, default 1.25). Explain the penalty on screen as a conservatism assumption.
- Show a warning that inference below the historical cutoff is extrapolation.
- **Sensitivity strip (required):** every simulation and optimiser result must be re-costed at penalties **1.0, 1.25, 1.5 and 2.0**, shown as a small table or chart.
- **Breakeven penalty (required):** report the penalty value at which the recommended strategy first breaches the bad-rate constraint. If that value is close to the default, the recommendation is fragile and the UI must say so.

### 9.4 Near-cutoff inference anchor

Override-approved applicants (5.2.1) give genuine observed performance below the cutoff. Use it —
but **compare like with like.**

Overrides are drawn from a deliberately marginal slice: bureau_score 650–699 **and** FOIR 0.50–0.60.
Comparing that slice against *all* declines in the same score band mixes two effects — the selection
effect you want to measure, and a FOIR mix effect you do not. In this dataset the mix effect is the
larger of the two and **reverses the sign of the comparison**: measured across the whole score band
the override population looks slightly worse than the declines, while within a matched FOIR band it
is substantially better. A comparison conditioned on score alone will therefore display a number
that contradicts the warning printed above it. Condition on FOIR as well.

- Compare **within segmentation cells** (the 10.2.2 dimensions: score band × FOIR band × employment_type), never within score bands alone. Show only cells holding at least `min_anchor_obs` override-approved customers (config, add it; default 200).
- For each such cell show, side by side: the **observed** bad rate of override-approved customers (count and 95% confidence interval), the **inferred** PD the model assigns to declined customers **in that same cell**, and the count of those declines.
- Report the **implied empirical penalty** = observed ÷ mean model PD, per cell, plus a volume-weighted total across cells.
- **State what that ratio is not.** It conflates two effects that cannot be separated without the oracle: the *selection effect* (overrides were human-picked and should outperform their cell) and *model calibration error on declines* (the model may simply be conservative in that band). A ratio below 1 is therefore evidence of one or the other, not proof of selection. On real data the two are not separable at all — say so on screen rather than labelling the ratio a selection estimate.
- **Validate the direction before displaying it.** Also compute the naive version (same score band, any FOIR) and show the two side by side. If they disagree in sign, say so on screen — that gap *is* the mix effect, and demonstrating it is more valuable than hiding it.
- Display with the warning that **override approvals were human-selected and are therefore favourably biased within their cell** — the observed rate is a lower bound on that cell's true rate, so the implied penalty is a lower bound on the penalty you should use.
- Sanity check, not a target: in the current synthetic data the measured within-cell implied penalty is about **0.9**, while the *true* within-cell selection effect — checkable only against the oracle in 10.4 — is approximately **zero**, and the model's PD for declines is close to their true bad rate. The generator's overrides favour low-risk applicants, but inside a narrow cell there is little residual risk variation left to select on, so the selection shows up *across* cells, not within them. A near-zero within-cell effect is the expected result here, not a sign that the comparison is still confounded. Report what you measure; do not tune towards a number.
- Let the user adopt the implied penalty in the UI, but do not make it the default. Section 10.4 checks it against the synthetic oracle.

## 10. Simulation and optimisation

### 10.1 What-if simulation

- Inputs: edited parameters for relaxable rules (score cutoff, FOIR cap, thin-file vintage, DPD/enquiry thresholds), plus on/off toggles for relaxable rules, plus any loaded segment overrides.
- Outputs, baseline vs scenario:
  - approval count and rate
  - incremental approvals (swap-ins) and removed approvals (swap-outs)
  - portfolio bad rate, split into observed / inferred / blended, plus the model-basis baseline (Sections 6 and 6.1)
  - **`NOT_MODELLED` swap-in count and share**, reported separately and excluded from the blended rate
  - scenario waterfall
  - swap-in breakdown by score band, FOIR band and employment type, with inferred bad rate per group — with `NOT_MODELLED` shown as its own row, not omitted
  - the sensitivity strip from 9.3
- Portfolio bad rate formula: (Σ observed bad_flag of retained booked + Σ inferred PD of modelled swap-ins) / (retained + modelled swap-ins).
- If relaxing R3_THIN_FILE or R4_BUREAU_HIST pushes swap-ins outside training support, the UI must show a blocking-style warning: "N of these approvals cannot be scored by the model. The bad rate shown covers only the remainder."
- Response time under 3 seconds.

### 10.2 Optimiser (greedy, explainable)

- Constraint: blended portfolio bad rate ≤ `max_bad_rate` (config, default 0.035; editable in UI).
- Candidates: historically declined applicants whose **only** failed rules are among R5_SCORE and R6_FOIR, and who are inside training support (i.e. have a PD).
- Group candidates into segments along **config-driven dimensions** (10.2.2). Default: score band (20 points, e.g. 680–699) × FOIR band (≤0.35, 0.35–0.50, 0.50–0.60) × employment_type. Ignore segments with fewer than `min_segment_size` (config, default 500).
- Sort segments by inferred bad rate, ascending. Add each segment if the portfolio stays within every active constraint. If not, skip it and continue to the next segment. Stop after `max_segments_added` segments (config, default 10) so the recommendation stays human-readable.
- Must be **deterministic**: identical input and config produce an identical segment list and headline.
- Output:
  - headline: current approval rate, proposed approval rate, incremental approvals, expected blended bad rate, constraint, and the count of candidate segments **rejected** by the constraint
  - the **share of incremental approvals drawn from THIN cells** (9.2), as a headline number beside the approval rate. Ascending-risk ordering selects preferentially for cells with little observed evidence, so this is not a footnote: it is the honest health warning for the whole recommendation.
  - the **candidate funnel**: total declines → failed only R5/R6 → inside training support → in segments of at least `min_segment_size`. In the current data roughly a third of declines have no PD at all, so "we found ten segments" means nothing without the denominator it came from.
  - the list of added segments as human-readable rules, e.g. "Approve score 680–699 AND FOIR ≤ 35% AND salaried". Each shows its count, inferred bad rate, the cumulative portfolio bad rate after adding it, and its **joint-support count with a THIN flag** (Section 9.2)
  - the added-segment counts must **reconcile to the headline incremental approvals**. Segment overrides also approve rows that no segment ever evaluated — applicants matching the override conditions but outside training support — so the table needs a `NOT_MODELLED` row of its own, exactly as 10.1 requires for the swap-in breakdown. In the current data that remainder is ~2,900 approvals whose true bad rate is 7.1%, and an unexplained gap between the table and the headline is how it stays invisible.
  - the list of **rejected** segments with the reason, so the user can see where the appetite ran out
  - **which constraint stopped the greedy**, as a field of its own, not something the reader infers from the rejection reasons. Two stops mean different things: appetite-bound means the strategy spent its whole risk budget, `max_segments_added`-bound means it ran out of *rule slots* with budget still unspent. Any comparison between two optimiser runs — the naive one in 10.2.3, the trade in 10.3, a saved scenario — is only like-for-like when both sides stopped for the same reason.
  - **Naive comparison** (10.2.3)
  - the sensitivity strip and breakeven penalty from 9.3
- The optimiser's recommendation can be loaded into the What-if page as segment overrides, and exported per 10.5.

#### 10.2.1 Constraints as configuration

Express constraints as a list in `config.yaml`, evaluated generically:

```yaml
constraints:
  - name: bad_rate
    metric: blended_bad_rate
    operator: "<="
    threshold: 0.035
    enabled: true
```

Only `blended_bad_rate` is implemented. Adding expected loss, fraud rate or profitability later must be a config entry plus one metric function — not a rewrite of the optimiser. Unimplemented metrics named in config must raise a clear error, not be ignored.

#### 10.2.2 Segmentation dimensions as configuration

Segment dimensions and their banding come from config, not from hard-coded column names:

```yaml
segmentation:
  - column: bureau_score
    type: band
    edges: [640, 660, 680, 700]
  - column: foir
    type: band
    edges: [0.0, 0.35, 0.50, 0.60]
  - column: employment_type
    type: categorical
```

Adding `bureau_vintage_months` or `enquiries_6m` as a dimension must require no code change.

#### 10.2.3 Naive comparison

The lowest uniform score cutoff (all other rules unchanged, no segment overrides) that keeps the portfolio within the same constraints.

- Search in **1-point steps from 700 down to 300**; take the lowest cutoff that still satisfies every constraint.
- Cost it on **exactly the same inferred basis** as the targeted strategy, including the same penalty and the same `NOT_MODELLED` exclusion.
- Compare at equal bad rate, on approval count.
- The demo must show the targeted strategy beating or matching the naive one. If it does not, report that plainly in the phase summary rather than tuning until it does.

### 10.3 Swap-out analysis (better portfolio, not just more approvals)

The question is "where can I change the strategy for a better portfolio outcome", not only "who else can I approve". Add the reverse view, which uses **purely observed** data and needs no inference at all:

- Segment the **currently approved** population along the same dimensions as 10.2.2.
- **Ignore segments below `min_segment_size`** and report how many were excluded and what share of the booked population they cover. An observed rate is still a rate computed on a sample: ranking every cell by rate puts a three-customer segment at 66.7% at the top of the page, twenty-nine rows above the 64,673-customer segment at 4.5% that carries a quarter of all bads. In the current data 49 of 59 cells fall below `min_segment_size` and together hold 0.5% of the booked population. A page that opens with noise is worse than no page.
- Rank the surviving segments by **contribution to total bads**, descending, and show observed bad rate, count and a 95% confidence interval beside it. Contribution is what actually frees headroom; the rate alone is what makes a tiny cell look alarming. Offer rate-descending as a secondary sort, never as the default.
- **"Worst" means excess bads, not total bads.** The ranking above answers *where the bads are*; the decline list answers *which segments cost more than they are worth*, and they are not the same list. Ranked by contribution, the second-worst segment in the current data is 129,724 customers at a 2.1% bad rate — **below** the 2.86% portfolio average. Declining it sheds 2,719 bads and 129,724 approvals: arithmetically correct, and an answer to a question nobody asked. Build the decline list from segments whose observed bad rate is above the portfolio average **and whose 95% confidence lower bound is still above it**, ranked by *excess bads* = count × (segment rate − portfolio rate), descending. In the current data that gives 700+ / FOIR 0.35–0.50 / self-employed (+1,047 excess bads), 700+ / FOIR 0.35–0.50 / other (+539) and 700+ / FOIR 0.00–0.35 / self-employed (+254). Show the portfolio rate the comparison is made against, on screen, beside the list.
- Show the combined trade: declining the worst N approved segments frees bad-rate headroom; feed that headroom back into the optimiser and report the net effect — approvals lost, approvals gained, net approval rate, net blended bad rate. `N` comes from config (`swap_out_decline_count`, default 3); the UI lets the user move it.
- **The trade must be a real strategy, evaluated by the engine.** Build a `Strategy` carrying the declined segments as exclusions (7.2) and the optimiser's new segments as overrides, then put it through the same `simulate()` that produces every other headline in the product. Do not compute the net figures by arithmetic on the side. Overrides also approve rows that no segment ever evaluated: for the current trade's segments that is 72,022 supported approvals against 73,360 actual, the missing 1,338 being `NOT_MODELLED` — so hand-summed counts understate approvals and divide the blended rate by the wrong denominator, which is the exact defect 10.2 requires fixed one section earlier. Going through the engine is also what makes the trade exportable under 10.5 and checkable against the oracle under 10.4; a headline that can be neither exported nor validated has not really been computed.
- **Say what stopped each side of the comparison.** With the current `max_segments_added` of 10 the base optimiser is appetite-bound (3.50% against a 3.50% cap) while the trade is slot-bound (3.30%, 20bp of appetite unspent, all sixteen of its rejections reading "reached max_segments_added"). Reporting "−22,337 approvals" from those two runs charges the trade for a limit it never reached: raise the cap until appetite binds on both sides and the same trade costs −11,620. Show the binding constraint beside each headline, and when they differ, say so rather than printing the delta as if it were a finding.
- Expect the trade to come out negative on this data, and do not tune towards a positive number. The segments worth declining are large and sit at 700+; their replacements are smaller and sit below the cutoff, so swapping them one-for-one loses volume even when it improves the rate. That is the honest answer to "should I do this", and a swap-out page whose answer is always yes is a sales tool. What makes the page worth building is that the user can see the exchange rate — 138,838 approvals and 5,809 bads out, 116,501 approvals and a 2.15% retained rate in — and decide for themselves.
- Watch the retained baseline while you do it. The optimiser measures headroom against the **currently booked** population; under the trade the retained population is the booked book *minus* the excluded segments, so the observed-bad numerator and the count denominator must both move. Leaving `booked` as the baseline hands the trade free headroom it has not earned, and the error is invisible in the output.
- Every number on this page that refers to the existing book is `OBSERVED`. Label it as such; this is the most defensible figure in the product and it should be visibly so.

### 10.4 Validation (synthetic data only)

- For the current, naive and optimised strategies, show the **true** bad rate (from `true_bad`) next to the blended estimate.
- Also show the true bad rate of the `NOT_MODELLED` approvals, so the cost of excluding them is visible.
- Also show true vs inferred for the near-cutoff bands in 9.4, to check whether the conservatism penalty was adequate.
- Label the page clearly: "Synthetic oracle — not available with real data."

### 10.5 Strategy export

`strategy_io.py` exports the recommended strategy as versioned JSON:

```json
{
  "strategy_id": "uuid",
  "created_at": "iso8601",
  "parent_strategy_id": "uuid or null",
  "base_rules": {"R5_SCORE": {"cutoff": 700}, "...": {}},
  "segment_overrides": [
    {"bureau_score": [680, 700], "foir_max": 0.35, "employment_type": ["salaried"]}
  ],
  "constraints": [{"name": "bad_rate", "threshold": 0.035}],
  "expected": {"approval_rate": 0.465, "blended_bad_rate": 0.0345,
               "inferred_share": 0.14, "not_modelled_count": 0}
}
```

It must round-trip: export → import → re-simulate reproduces the same headline numbers. This is the object a Champion/Challenger framework would deploy; executing it is out of scope.

## 11. Build phases (stop after each)

| Phase | Scope | Done when |
|---|---|---|
| 1 | contracts, config, generator (incl. overrides), loader, rule engine, waterfall, sample fixture, tests | calibration targets in 5.3 met; reproduction excluding overrides = 100%; tests pass |
| 2 | risk model, training support, provenance labelling, simulation engine, headless CLI, tests | AUC ≥ 0.60 and calibration printed; support ranges printed; simulation under 3 s; tests pass |
| 3 | optimiser, naive comparison, **near-cutoff anchor (9.4)**, swap-out analysis, sensitivity and breakeven penalty, strategy export, validation calcs, tests | optimiser respects the constraint and rejects ≥ 1 segment; targeted ≥ naive; anchor computed within cells with the naive version shown beside it; export round-trips; tests pass |
| 4 | Streamlit UI (Section 12) | all pages render end-to-end on 1M rows; the optimiser page's added-segment counts visibly sum to its headline; THIN share, candidate funnel and binding constraint appear with the headline, not below the fold; no page recomputes a figure the 11.1 CLIs already return |
| 5 | README, cleanup, demo script | fresh-clone setup works in under 10 minutes |

### 11.1 Headless entry points (required from Phase 2)

Phases 1–3 must be verifiable without the UI. Provide:

- `python -m src.generate_data` — builds the dataset, prints the 5.3 calibration table.
- `python -m src.risk_model` — trains, prints AUC, calibration table, coefficients, support ranges.
- `python -m src.simulate --scenario <json>` — prints a JSON result block.
- `python -m src.optimise` — prints the full JSON headline, segment list, naive comparison and sensitivity strip.

All four print machine-readable JSON to stdout (a human-readable table to stderr is fine).

## 12. UI (Streamlit)

### 12.1 Ground rules

- **The UI computes nothing.** Every number on every page comes from the same function the 11.1 CLI calls — `build_waterfall`, `train_model`, `near_cutoff_anchor`, `simulate`, `optimise`, `swap_out_analysis`, `combined_trade`. No page recomputes a rate inline, not even a one-liner, and no page sums a table to produce a headline. Two of the three defects found in Phases 2 and 3 were a count reconstructed in a second place and then drifting from the first. A Streamlit page is the easiest place in this codebase for that to happen again and the hardest place to notice it.
- **Errors surface.** `ReproductionError`, the `KeyError` from an unknown rule parameter, the `ValueError` from a retained population that is not a subset of booked — these were added on purpose, because a silent wrong answer is the failure mode this whole product is about. Render them as a visible error with the message intact. No bare `except:`, and nothing that turns a raise into an empty dataframe and a green tick.
- **NaN is not zero.** A `NOT_MODELLED` population has no rate: render it as `—`, never `0.00%`, and never as an empty cell a reader will take for zero. Wherever a rate column can hold NaN, show the row's count beside it so the reader can see the population is real even though the rate is not.
- **Performance.** `st.cache_data` for the dataframe, `st.cache_resource` for the fitted model. The optimiser takes about 4 seconds on 1M rows and must not re-run on every widget movement: put it behind an explicit run button, keyed on the parameter tuple.

### 12.2 Pages

1. **Overview**: population size, baseline approval rate, observed bad rate, reproduction match rate (raw ~99.0% and, excluding `manual_override` rows, exactly 100%), override counts in both directions, performance-window assumption, data provenance note. If the second match rate is below 100%, this page says so in red and does not round it away (7.3).
2. **Decline waterfall**: sequential chart, the override adjustment step **derived from the `manual_override` flag** (8), the segment-exclusion step when the displayed strategy carries exclusions (7.2), single-rule declines, score × FOIR heatmap. The steps must sum to the application total on screen, visibly.
3. **Risk model**: AUC, calibration chart, coefficients, per-feature training-support ranges and out-of-support counts, and three things the support rules produce that are easy to leave out —
   - the count of applicants sitting **in a supported bin but outside the booked min–max** (9.2). If that count is zero on this data, something upstream is broken; show it rather than hiding a zero.
   - any **categorical level dropped for having no booked observations** (9.1), named, with its application count.
   - the **near-cutoff anchor** (9.4): the per-cell table with counts and confidence intervals, the volume-weighted total, the naive score-band-only version beside it, and both warnings — the selection-bias lower-bound warning and, when the two disagree in direction, the mix-effect warning quoting both measured penalties. Carry the 9.4 paragraph on what the ratio is *not* onto the page as text, not as a tooltip. A user who reads only this page must not leave believing the ratio is a selection estimate.
4. **What-if simulator**: parameter controls, baseline vs scenario KPIs, the observed / model-basis / inferred / blended split with the 6.1 explanation of why the model-basis baseline is the honest comparator, the `bias_warning_ratio` warning when it and the observed baseline diverge, the `NOT_MODELLED` panel, the swap-in breakdown **including its `NOT_MODELLED` row and its joint-support count with THIN flag** (10.1), and the sensitivity strip. Editing a rule parameter that does not exist must raise into the UI (7.2), not be swallowed by the widget layer. Scenarios load from and save to the same JSON the 11.1 CLI accepts.
5. **Optimiser**: constraint input, run button, then —
   - the headline approval count and rate, blended bad rate against the constraint, and **the share of incremental approvals drawn from THIN cells** beside it, labelled with its denominator (94.4% of *evaluated* swap-ins, 92.0% of the headline incremental figure — they are not the same number and the page must say which it is showing).
   - **which constraint stopped the greedy** (10.2), beside the headline, not buried in the rejected table.
   - the **candidate funnel** as a funnel: 601,354 declines → 387,944 failing only R5/R6 → 319,214 inside training support → 172,531 in viable segments. Ten segments out of a starting pool the reader cannot see is a number without a denominator.
   - the added-segment rules table with count, inferred bad rate, cumulative portfolio bad rate, joint-support count and THIN flag, **and the `NOT_MODELLED` row that makes the table reconcile to the headline** (10.2). The column must add up to the headline on screen; if it does not, that is the bug, not a rounding note.
   - the rejected-segment table with reasons, the naive comparison chart, the sensitivity strip, the breakeven penalty, and the export button.
6. **Portfolio quality** — the swap-out page (10.3), and the only page in the product that needs no inference at all. It carries the whole of 10.3, which has changed twice and is easy to under-build:
   - the diagnostic ranking of currently approved segments by **contribution to total bads**, with count, observed bad rate and its 95% confidence interval, and cumulative share. Rate-descending is a secondary sort, never the default. State how many segments fell below `min_segment_size` and what share of the book they cover (49 of 59, 0.5%).
   - the **decline list**, which is a different list: segments whose rate *and* whose CI lower bound are above the portfolio rate, ranked by excess bads. Show the portfolio rate the comparison is made against.
   - the **combined trade**, with the binding constraint on both sides. When they differ the page shows both and withholds the delta, exactly as the CLI does; a labelled wrong number still gets quoted in a meeting.
   - every figure on this page labelled `OBSERVED`.
7. **Validation** (synthetic only): the 10.4 oracle comparisons — predicted versus true for the strategy and for the near-cutoff anchor — each with the reported number, the true number and the gap. The page states plainly that it exists only because the data is synthetic and has no counterpart on real data, and it must degrade cleanly to that message when `true_bad` is absent rather than raising.
8. **Next steps**: static text covering Champion/Challenger (referencing the exported strategy object), additional constraints, and existing-book use cases.

### 12.3 Display rules

- Show provenance labels as visible badges or suffixes next to **every** bad-rate figure, including inside tables.
- Every page with a results table offers CSV/JSON download.
- Warn when the inferred share of approvals exceeds `max_inferred_share` (config, default 0.50). At default settings the recommendation sits at 21.6%, so this path does not fire on the shipped configuration — exercise it once with a lowered threshold and make sure the warning renders.
- The app must run every page end-to-end on the 1M-row dataset. If a page cannot, cut the page's scope rather than sampling the data behind the user's back.

## 13. Tests (minimum)

Tests run against `tests/fixtures/sample.parquet` (~500 rows, committed) unless the test genuinely needs scale. The full `pytest` run must finish in **under 60 seconds** and must not require the 1M-row dataset. `config.yaml` must support an `n_rows` override so a small dataset can be generated on demand.

- Rule engine reproduces historical decisions at 100% for all non-override rows.
- The set of reproduction mismatches equals exactly the set of `manual_override == True` rows.
- Waterfall counts sum to total applications, including the override adjustment step.
- Mandatory rules cannot be relaxed by the simulator or optimiser; a segment override cannot approve an age or fraud failure.
- Portfolio bad-rate formula is correct on a small hand-built fixture, including a case with `NOT_MODELLED` rows present.
- `predict_pd` returns NaN for out-of-support rows, and a categorical level with no booked observations is dropped rather than given a zero coefficient.
- Relaxing R4_BUREAU_HIST in a simulation produces `NOT_MODELLED` swap-ins that are excluded from the blended bad rate.
- `cell_support` returns the true in-cell booked count on a hand-built fixture, and a cell below `min_cell_obs` is flagged THIN in the optimiser output.
- Joint support is independent of marginal support: a row that passes every marginal check but sits in an empty cell still gets a PD, and still reports a joint-support count of zero.
- The 9.4 anchor comparison is computed within segmentation cells, not score bands — asserted on a fixture built so the two give opposite signs.
- Optimiser output never exceeds the constraint, and is deterministic across two runs with identical input.
- Swap-ins never include no-hit / thin-file or mandatory-rule failures.
- Naive comparison is costed on the same basis as the targeted strategy.
- Strategy export round-trips to the same headline numbers, including a strategy carrying exclusions.
- A segment exclusion declines every applicant it covers, no override can approve one back, and the 10.3 trade's net figures equal a full `simulate()` of the same strategy.
- The optimiser reports which constraint stopped it, and reports `max_segments_added` — not the bad-rate cap — when the slot limit is the binding one.
- The generator is deterministic for a given seed.
- The committed fixture equals a fresh rebuild from the generator, so it cannot go stale behind a passing suite.
- Editing a rule parameter that does not exist raises rather than running as a silent no-op.
- The waterfall's override adjustment step is derived from `manual_override`; a non-override disagreement raises.
- An applicant whose feature value sits in a supported bin but outside the booked range is `NOT_MODELLED`.
- **`test_ui.py` must render, not import.** Executing a page module proves only that its imports resolve; every
  figure on every page lives inside a function body that a bare import never enters. Drive each page with
  `streamlit.testing.v1.AppTest` against the committed fixture, assert `at.exception` is empty, and **click the run
  button** on the optimiser and swap-out pages, because the half of those pages that matters does not execute until
  something is clicked. A page that raises `NameError` on a code path no test enters is a broken build with a green
  suite, which is worse than a red one.
- A scenario JSON written by the UI and read back by the 11.1 CLI produces identical headline numbers, and vice
  versa — assert on `blended_bad_rate`, not just on the file parsing. Every key the spec accepts, `inference_penalty`
  included, must survive the trip; a spec key the UI silently ignores is the same defect as a wrong number.
- Each oracle row on the validation page is built from the strategy that actually produced it. Assert the naive row's
  approval count equals `naive_result.approval_count`; pairing one strategy's approvals with another's estimate
  produces a plausible row that is true of neither.
- **`test_leakage.py`**: scan every file in `src/` except `generate_data.py` and `validation.py` for the string `true_bad` and fail on any occurrence.

## 14. Acceptance criteria

- `python -m src.generate_data` builds the dataset and prints calibration results within the 5.3 targets.
- `pytest` passes, in under 60 seconds, without the 1M-row dataset.
- All four headless commands in 11.1 emit valid JSON.
- `streamlit run app/streamlit_app.py` runs all pages on 1M rows without errors.
- The optimiser shows more approvals than baseline, a blended bad rate within the constraint, and a targeted strategy that beats or matches the naive cutoff reduction.
- **The constraint binds**: the optimiser rejects at least one candidate segment. If it accepts everything, there is no optimisation story — report this rather than shipping it.
- Incremental approvals are between 3 and 12 percentage points of the application population.
- Every bad-rate number carries a provenance label, and no `NOT_MODELLED` population is silently folded into a headline. A missing rate renders as `—`, never as `0.00%` or an empty cell.
- No page under `app/` recomputes a headline figure. Each reads it from the same function the corresponding 11.1 CLI calls, and the optimiser page's segment table reconciles to its own headline on screen.
- The UI surfaces `ReproductionError` and the unknown-rule-parameter `KeyError` as visible errors. A run that swallows either is a failed build, not a passing one.

## 15. Interface contracts (write `contracts.py` first; do not deviate)

```python
from dataclasses import dataclass
from typing import Optional
import pandas as pd

@dataclass(frozen=True)
class Rule:
    id: str                  # "R5_SCORE"
    params: dict             # {"cutoff": 700}
    mandatory: bool
    enabled: bool = True

@dataclass(frozen=True)
class SegmentOverride:
    conditions: dict         # {"bureau_score": (680, 700), "foir_max": 0.35,
                             #  "employment_type": ["salaried"]}
    relaxes: tuple           # ("R5_SCORE", "R6_FOIR") — rules this override may bypass

@dataclass(frozen=True)
class SegmentExclusion:
    conditions: dict         # same shape as SegmentOverride.conditions
    reason: str              # decline reason shown in the waterfall, e.g. "SWAP_OUT_700+_FOIR35-50_SE"

@dataclass(frozen=True)
class Strategy:
    rules: tuple             # tuple[Rule, ...] in evaluation order
    overrides: tuple = ()    # tuple[SegmentOverride, ...]
    exclusions: tuple = ()   # tuple[SegmentExclusion, ...] — approve -> decline, never relaxable (7.2)

@dataclass
class ScenarioResult:
    approval_count: int
    approval_rate: float
    swap_in_count: int
    swap_out_count: int
    not_modelled_count: int          # approvals with no PD; excluded below
    observed_bad_rate: float         # OBSERVED, retained booked
    model_basis_baseline: float      # PREDICTED, baseline booked (Section 6.1)
    inferred_bad_rate: float         # INFERRED, modelled swap-ins
    blended_bad_rate: float          # excludes not_modelled
    inferred_share: float
    waterfall: pd.DataFrame
    swap_in_breakdown: pd.DataFrame  # includes a NOT_MODELLED row and a booked_in_cell column
    sensitivity: pd.DataFrame        # penalty -> blended_bad_rate

@dataclass
class OptimiserResult:
    headline: ScenarioResult
    added_segments: pd.DataFrame     # conditions, count, inferred_bad_rate, cumulative_bad_rate,
                                     # booked_in_cell, thin
    rejected_segments: pd.DataFrame  # conditions, count, inferred_bad_rate, reason
    naive_cutoff: float
    naive_result: ScenarioResult
    breakeven_penalty: float
    strategy: Strategy
    thin_share: float               # THIN share of EVALUATED incremental approvals (9.2)
    thin_share_of_total: float      # THIN share of the HEADLINE incremental figure — the same
                                    # numerator over a denominator that includes NOT_MODELLED
    binding_constraint: str         # "bad_rate" | "max_segments_added" | "none" — what stopped the greedy
    candidate_funnel: CandidateFunnel  # declines -> only R5/R6 -> in support -> in viable segments
```

Required function signatures:

```python
# rules.py
def evaluate_strategy(df: pd.DataFrame, strategy: Strategy) -> pd.DataFrame:
    """Returns, aligned to df.index:
       decision            category  approve/decline
       first_failed_rule   str|None
       failed_<RULE_ID>    bool      one column per rule
       approved_by_override bool
    """

# risk_model.py
class RiskModel:
    def fit(self, booked: pd.DataFrame) -> "RiskModel": ...
    def predict_pd(self, df: pd.DataFrame) -> pd.Series:
        """Model PD. NaN for rows outside training support."""
    def support_mask(self, df: pd.DataFrame) -> pd.Series:
        """True where the model is entitled to produce a PD."""
    def support_summary(self) -> pd.DataFrame:
        """Per feature: supported range or levels, booked obs count."""
    def cell_support(self, df: pd.DataFrame) -> pd.Series:
        """Booked training observations in each row's segmentation cell (Section 9.2).
           An evidence count only — it never changes a decision or a PD."""

# simulate.py
def simulate(df: pd.DataFrame, baseline: Strategy, scenario: Strategy,
             model: RiskModel, config: dict) -> ScenarioResult: ...

# optimise.py
def optimise(df: pd.DataFrame, baseline: Strategy, model: RiskModel,
             config: dict) -> OptimiserResult: ...
def swap_out_analysis(df: pd.DataFrame, baseline: Strategy,
                      config: dict) -> pd.DataFrame:
    """OBSERVED-only ranking of currently approved segments by bad rate."""
```

---

# Part B — Platform requirements

*Added 2026-09-19. Supersedes Part A wherever the two conflict.*

### Traceability — the twenty-two new requirements

| # | Requirement as stated | Where it is specified |
|---|---|---|
| 1 | Not a demo | 0, 16.1, 17 |
| 2 | Deliverable to a bank in Saudi Arabia | 16.1, 16.2, 16.3, 31.4 |
| 3 | Deployed on client on-premise or their cloud (likely Oracle) | 18, 31.3 |
| 4 | Integrated with the client's database | 22.1, 22.2, 22.3 |
| 5 | Three days to deliver | 17 — the three days is the CxO demo; deployment to both clients is the second week of October 2026. **Read Section 17 before planning anything.** |
| 6 | Login module | 20.1 |
| 7 | Subscription enforcement / "golden key" | 21 |
| 8 | Multiple users | 20.1, 20.2 |
| 9 | Configurable, but not replicable by the client | 30 |
| 10 | Patches integrate without disturbing customer configuration | 23.5, 24 |
| 11 | Multiple databases and APIs, configurable | 22 |
| 12 | Multi-tenant — data, config, strategies, models isolated | 19 |
| 13 | Role-based access, maker/checker, full audit trail | 20.2, 20.3, 20.4 |
| 14 | Versioning and rollback, with comparison and restore | 23.1, 23.2, 23.4 |
| 15 | Sandbox → test → production | 23.3 |
| 16 | Configuration separated from the core engine | 18.1, 18.2, 23.5, 24.3 |
| 17 | Explainability — why, expected impact, driving constraint | 26 (extends 10.2) |
| 18 | Open modelling layer — our models and external ones | 25 |
| 19 | Champion/challenger and experimentation | 27 |
| 20 | Monitoring — data quality, performance, drift, API failures | 28 |
| 21 | Generic across originations, existing book, collections, limits, pricing | 29 |
| 22 | A reusable decision + simulation + optimisation platform, not an approval tool | 16.4, 29 |

Two things came out of writing this down that were not on the list and are worth flagging here
rather than leaving in a section: **regulatory rules need to be their own rule class** (16.3 — SAMA
affordability limits must be unreachable by the optimiser), and **the entire synthetic dataset is
Indian** (16.2, 31.4 — rupees, CIBIL-shaped scores) and cannot be shown to this client.

## 16. Product context

### 16.1 What changed

| Assumption in Part A | Reality |
|---|---|
| Demo-grade prototype | Contracted deliverable to a client |
| Anonymous single user on a laptop | Multiple named users inside a bank |
| Synthetic Parquet file | The client's own database, plus APIs |
| `streamlit run` on the developer's machine | Client's on-premise estate or their private cloud (Oracle Cloud Infrastructure is the likely target) |
| No auth, no tenancy, no audit | Regulated financial institution: identity, RBAC, maker-checker, full audit trail |
| Ships once | Ships, then receives patches without disturbing the client's configuration |
| No commercial enforcement | Subscription-billed, with entitlement enforcement (Section 21) |

### 16.2 The clients and the jurisdiction

**The same requirement has arrived from two existing clients**, and the product deploys into both.
Three facts follow from "existing" that change the engineering, and each is worth more than it
first looks:

- There is an **existing commercial relationship and contract vehicle**. Licensing (Section 21) is a
  contract amendment or renewal, not a new negotiation — and the enforcement ladder can be
  introduced as part of a subscription move rather than dropped on them.
- There is an **existing patch channel**: the dev team already ships encrypted patches to both.
  Requirement 10 is therefore not theoretical — it is a live operational pain, and Section 24 should
  be built to ride the channel that already exists rather than inventing a second one.
- **Two clients is the moment configuration separation stops being architecture and starts being
  survival.** Two banks with diverging requirements on one codebase is how a small product company
  ends up maintaining two forks, and the fork is invisible for about four months and then
  permanent. Sections 18.2, 23.5 and 24.3 exist for exactly this; if they are skipped, the second
  client's first custom requirement becomes an `if client == ...` and the product is over.

At least one client is a **bank in the Kingdom of Saudi Arabia**. The jurisdiction notes below apply
to that deployment; confirm whether they apply to the second. The engineering consequences are easy
to miss because the engine was built against Indian synthetic data:

- **Currency is SAR, not INR.** `monthly_income`, `loan_amount`, `existing_emi`, `proposed_emi`
  are currency-typed fields, and every display must be locale-formatted. The synthetic generator's
  distributions (median income ₹45,000, median loan ₹300,000) are Indian and are **demo data only**;
  they must never appear in a client-facing build. See 31.4.
- **The bureau is SIMAH, not CIBIL.** Score range, no-hit semantics, enquiry definitions and DPD
  bucketing all come from SIMAH's schema and must be mapped, not assumed. The mapping lives in the
  configuration layer (Section 22.3), not in code.
- **Affordability is regulated.** SAMA caps the Debt Burden Ratio for consumer lending. The engine's
  `R6_FOIR` is conceptually the same quantity, but in Saudi it is **partly a regulatory limit, not a
  commercial preference** — and a regulatory limit must not be relaxable by the UI or reachable by
  the optimiser. This is the single most important localisation change: see 16.3.
- **Regulatory regime**: SAMA rules for consumer finance and for model risk/governance; the Saudi
  **PDPL** for personal data (including data residency and cross-border transfer restrictions);
  **NCA ECC** controls for a bank's information systems. Practical consequence: the deployment is
  air-gapped or heavily egress-restricted, data does not leave the Kingdom, and no telemetry,
  crash reporting or license heartbeat may assume outbound internet. Design offline-first (21.3).
- **Localisation**: Arabic/RTL support in the UI, Arabic text in names and free-text fields
  (UTF-8 end to end, correct collation), Hijri date display alongside Gregorian, `Asia/Riyadh`
  as the display timezone with **UTC stored everywhere**, and a Sunday–Thursday working week in any
  scheduling or SLA logic.

### 16.3 Regulatory rules are a third rule class (required)

Part A Section 7.1 has two rule classes: mandatory (`R1_AGE`, `R2_FRAUD`) and relaxable. That is not
sufficient. A rule can be commercially relaxable in one jurisdiction and legally fixed in another,
and the same binary flag cannot express both.

Add a `regulatory` flag to `Rule` (Section 15, extended in 29.5):

- `mandatory: true` — the engine will never approve a failing applicant, by any path.
- `regulatory: true` — implies `mandatory`, **and** the parameter value itself is locked: it cannot
  be edited in the UI, cannot be moved by the optimiser, cannot be relaxed by an override, and
  cannot be changed by a tenant administrator. Changing it requires a configuration change signed
  off through maker-checker with a regulatory-reference field recorded in the audit log.
- A regulatory rule's decline reason must be labelled as such in the waterfall, because
  "we declined 40,000 people for regulatory reasons" and "we declined 40,000 people because of our
  own appetite" are answers to different questions and the bank will be asked both.

**The optimiser must never emit a recommendation that breaches a regulatory rule.** A test must
assert that a segment override cannot bypass a rule flagged `regulatory`, using the same fixture
pattern as the existing mandatory-rule test (Section 13). A product that recommends a SAMA breach
to a Saudi bank is not a product with a bug; it is a product that cannot be sold again.

### 16.4 What the client is buying

State this plainly because it drives every architectural decision in Part B: the client is not
buying an approval-rate calculator. They are buying a **reusable decision, simulation and
optimisation platform** — one engine that can be pointed at originations today and at existing-book
actions, collections treatment, limit management and pricing tomorrow, without a rebuild
(Section 29). Building it narrowly around approval-rate optimisation would produce a very good
single-purpose tool and foreclose the actual product.

## 17. Delivery plan and timeline

### 17.1 The actual dates

| Date | Event |
|---|---|
| **2026-09-22** (3 days) | CxO demo, to each client separately |
| **~2026-09-26** (7 days) | Client database schema expected; the owner is on leave until then |
| **2026-10-08 → 2026-10-14** | Deployment to both clients' on-premise or private cloud |

So there are two different builds with two different jobs, and conflating them is the main risk:

- **The demo build (3 days)** has to win a room. It is judged on whether the analysis is credible
  and the product looks like it belongs in their bank. It is not judged on multi-tenancy.
- **The deployable build (~3.5 weeks)** has to survive installation, a security review and real
  users. It is judged on auth, audit, packaging, and whether it runs on their data.

Three and a half weeks to deployment is tight but not unreasonable **provided the scope is T1 plus
the parts of T2 that gate installation** (Section 17.4), and provided nothing in Part B beyond that
is attempted. The plan below is sized to those two dates, not to the full Part B.

### 17.2 Why the full Part B is not a three-week project

Section 16 and Sections 18–31 describe multi-tenancy,
authentication, RBAC with maker-checker, an audit trail, licensing and entitlement enforcement,
pluggable database and API integration, configuration versioning with sandbox/test/production
promotion, non-disruptive patching, an open modelling layer, champion/challenger execution, a
monitoring stack, and a generic multi-domain decision abstraction — deployed inside a Saudi bank's
estate and integrated with their data.

**That is a six-to-twelve month programme for a small team.** The three-week window delivers a
credible, installable product against a well-chosen subset; it does not deliver the platform.

The failure mode to avoid is shipping a thin imitation of all twenty-two requirements — a login page
with a hardcoded password, a `tenant_id` column nothing enforces, a licence check one environment
variable disables. A bank's security review finds every one of them, and with an *existing* client
the finding costs more than it would with a stranger, because it retrospectively devalues whatever
they already trust.

### 17.3 Tranches

Sequenced so that each tranche is independently demonstrable and nothing in a later tranche requires
rewriting an earlier one.

| Tranche | Contents | Notionally |
|---|---|---|
| **T0 — Engine** (Part A, Phases 1–5) | Rules, waterfall, risk model, provenance, simulation, optimiser, swap-out, validation, Streamlit UI. Mostly built. | Done / finishing |
| **T1 — Demo build** | Section 17.4. Wins the room; not installed anywhere. | by 2026-09-22 |
| **T2 — Deployable build** | Section 17.5. Everything that gates installation and security review. | by 2026-10-08 |
| **T3 — Platform** | Multi-tenancy enforcement, sandbox→test→production promotion, the migration framework, open modelling layer, monitoring, adapters beyond the first. | Q4 2026 |
| **T4 — Decision platform** | Champion/challenger execution and measurement, the domain-pack abstraction (Section 29), second domain (existing-book or collections). | 2027 |

### 17.4 T1 — the demo build (by 2026-09-22)

The audience is a CxO, twice, separately. What persuades that audience is that the analysis is
*right* and that the product looks like it was built for their bank. Priority order:

1. **Part A, finished.** Phases 3–5: optimiser, swap-out, validation, the Streamlit UI, and a green
   test suite. This is the demo. Everything else on this list is presentation around it.
2. **Localisation** (16.2, 31.4): SAR, SIMAH-shaped bureau score, DBR rather than FOIR, plausible
   Saudi employment categories. An Indian-rupee screen in front of a Saudi CxO reads as a
   repurposed side project and that impression does not recover.
3. **The regulatory rule class** (16.3). Two hours of work, and it answers the question their credit
   risk head will actually ask — "can this thing recommend breaching the SAMA DBR cap?" — with
   "structurally impossible, and here is the test that proves it."
4. **A dummy client schema to map from** (17.6). Demonstrates requirement 4 on stage without any
   client data, and converts to the real schema as a config change when it arrives.
5. **A login screen and a licence page**, thin but real. These exist in the demo to make the T2
   story concrete, not to be secure yet.
6. **The architecture story for requirements 9–22** as a deck, backed by Part B of this document.
   For twelve of the twenty-two requirements, a clear architecture answer at CxO level is worth more
   than a half-built implementation, and is the honest thing to present.

What T1 must not do is make an architectural choice that T2–T4 have to undo: that is the purpose of
Sections 18 and 29.

### 17.5 T2 — the deployable build (by 2026-10-08)

Everything that gates installation and a security review, and nothing else:

1. **`RunContext` and configuration out of the engine** (18.2, 23.5, 24.3). Do this first. With two
   clients diverging from one codebase, it is the difference between a product and two forks, and
   it gets an order of magnitude more expensive with every week of new code written without it.
2. **Identity**: OIDC against each client's IdP, with the local-account fallback (20.1). Ask both
   clients for IdP details *now* — it has the longest lead time of anything on this list.
3. **RBAC and maker-checker** (20.2, 20.3) — a strategy cannot reach production without a second
   person approving it. Banks will ask; it is also genuinely cheap once configuration is versioned.
4. **Append-only, hash-chained audit log** (20.4). Cannot be backfilled. Build it in T2 or explain
   its absence for the life of the deployment.
5. **Persistence**: Postgres or Oracle for users, roles, audit, configuration versions and results.
6. **Field mapping and the data-readiness report** (22.3), against the real schema once it arrives.
   This is the step that decides whether "integrated with the client's database" takes a week or a
   quarter, and the readiness report is the artefact that makes the delay legibly theirs rather than
   ours when their data is not what they said it was.
7. **Signed licensing with the full enforcement ladder and licence page** (21.3, 21.5, 21.6),
   delivered through the existing encrypted patch channel, with the contract amendment alongside it.
8. **Packaging and deployment**: container images, offline/air-gapped install bundle, runbook,
   smoke test (31.3).

Explicitly *not* in T2: multi-tenancy enforcement (both deployments are single-tenant — write
tenant-clean code, build none of the machinery), sandbox→test→production promotion, champion/
challenger, the monitoring stack, the open modelling layer, domain packs. Each is designed in
Part B and scheduled in T3/T4.

### 17.6 Working before the schema arrives

The client schema is expected around 2026-09-26. Until then, do not block and do not guess:

- Build a **plausible bank LOS + bureau schema** as the mapping *target* — ugly column names,
  `VARCHAR` dates, sentinel nulls (`0`, `-1`, `9999`), single-character decision codes, a
  five-valued decision field where the spec says two. Make it awkward on purpose; a clean dummy
  schema tests nothing.
- Drive it through the field-mapping layer (22.3) into the canonical Section 5.1 schema. When the
  real schema lands, the change is a mapping YAML, which is precisely the claim requirement 11
  makes. If it turns out to be a code change, the mapping layer was not finished.
- Send the client the **canonical schema and the data-readiness questionnaire now**, ahead of the
  extract. The schema owner being on leave is a reason to have the request sitting in their inbox
  on the day they return, not a reason to wait a week.

## 18. Architecture

### 18.1 Layers

Four layers, with a strict dependency direction. Nothing points upward.

```
  UI / API              app/, api/        presentation only; computes nothing (12.1)
        |
  Platform services     platform/         identity, tenancy, licensing, audit, config store,
        |                                 run orchestration, monitoring
        |
  Domain packs          domains/          originations, existing-book, collections, limits,
        |                                 pricing — declarative (Section 29)
        |
  Core engine           core/             rules, waterfall, risk model, provenance, simulate,
                                          optimise — tenant-agnostic, stateless, no I/O
        |
  Adapters              adapters/         data sources, model providers, auth providers,
                                          secret stores, notification sinks
```

- **`core/` is the IP.** It is pure computation: dataframe in, result out. It has no knowledge of
  tenants, users, licences, databases or HTTP. It is shipped as a versioned wheel and is the only
  part of the system that is upgraded as a unit (Section 24).
- **`core/` must never read global state.** No module-level `config.yaml` load, no `os.environ`, no
  singletons. Every entry point takes an explicit `RunContext` (18.2). This one rule is what makes
  multi-tenancy, configuration versioning and reproducible runs possible; retrofitting it after the
  fact means touching every function in the engine.
- **Adapters are the only code allowed to do I/O.** A `core/` module that opens a database
  connection is a defect, and a test should enforce it the way `test_leakage.py` enforces the
  `true_bad` boundary (13): scan `core/` for `connect`, `requests`, `open(`, `os.environ`.

### 18.2 `RunContext` (required)

Every engine entry point — `evaluate_strategy`, `build_waterfall`, `train_model`, `simulate`,
`optimise`, `swap_out_analysis`, `combined_trade` — takes a `RunContext` in place of the loose
`config: dict` in Section 15:

```python
@dataclass(frozen=True)
class RunContext:
    run_id: str                  # uuid, stamped on every output and audit record
    tenant_id: str
    environment: str             # "sandbox" | "test" | "production"
    actor: Actor                 # user id, roles, session id — for audit, never for logic
    config: ResolvedConfig       # immutable, fully resolved (24.3), carries config_version_id
    dataset_version: str         # the pinned data snapshot the run reads (22.5)
    entitlements: Entitlements   # feature flags from the licence (21.4)
    clock: Clock                 # injected; never call datetime.now() inside core/
```

Consequences worth stating because each of them is a defect avoided:

- A result is **reproducible**: `run_id` plus `config_version_id` plus `dataset_version` fully
  determine it. A bank asking "why did this recommendation change between Tuesday and Thursday" gets
  a diff, not a shrug.
- **Determinism survives.** Part A already requires the optimiser to be deterministic (10.2); an
  injected clock and an explicit config snapshot are what keep it deterministic across deployments.
- Cross-tenant contamination becomes a type error rather than a data-leak incident.

### 18.3 The UI computes nothing — extended

Part A Section 12.1 requires that no Streamlit page recomputes a figure. Part B extends the same
rule one layer out: **the API computes nothing either.** Every number returned to any client comes
from the same `core/` function the headless CLI calls. When the UI becomes a web front end served by
an API (T2+), the API layer is transport and authorisation only.

### 18.4 UI technology

Streamlit is correct for T0/T1 and wrong for T2 onward: it has no real session model, no per-widget
authorisation, awkward multi-user behaviour, and a security posture no bank will accept for a
multi-user internal application. Plan the migration to a served front end over an authenticated API
at T2, and **keep every page's logic in `core/` so that migration is a presentation rewrite only**.
That is the cash value of 12.1 and 18.3: the UI is disposable by design.

## 19. Multi-tenancy and isolation

Requirement 12: each customer's data, configuration, strategies and models must remain completely
isolated.

### 19.1 Deployment topologies

Two, and the code must support both from one build:

- **Single-tenant on-premise** (the Saudi bank, and most banks): a dedicated install, dedicated
  database, dedicated encryption keys. Isolation is physical. This is the T1/T2 target.
- **Multi-tenant hosted** (smaller clients, our own cloud): one install, many tenants, isolation
  enforced in software.

Do not treat the first as an excuse to skip the second's controls. A single-tenant install built on
multi-tenant-clean code costs nothing extra; a single-tenant install with `tenant_id` bolted on later
is a rewrite of every query.

### 19.2 Rules

- **Every persisted row carries `tenant_id`**, including audit records, model artefacts, datasets,
  configuration versions and experiment assignments.
- **No code constructs a query without a tenant scope.** All data access goes through a
  session-scoped repository that injects the tenant predicate from the `RunContext`. Where the
  database supports it (Postgres RLS, Oracle VPD), enforce it at the database layer *as well* —
  defence in depth, because the application-layer control is one forgotten `WHERE` clause away from
  failing silently.
- **A test must attempt cross-tenant access and assert it fails**, for every repository. Isolation
  that is never tested is isolation that is assumed.
- **Model artefacts are tenant-scoped.** A model fitted on tenant A's booked population must be
  incapable of being loaded into tenant B's run — enforce by storing the tenant in the artefact
  metadata and checking it at load, not by file path convention.
- **Secrets and encryption keys are per tenant.** A shared key means a shared blast radius.
- **Exports carry the tenant identity** and the run id, so a spreadsheet found in an inbox can be
  traced back to the run that produced it.

### 19.3 Data residency

For the Saudi client, all tenant data — including backups, logs and any diagnostic bundle we ask
them to send us — stays in the Kingdom unless the contract says otherwise and PDPL allows it.
Practical rule: **there is no "send us your data so we can debug it"**. Build the diagnostic bundle
(28.5) to be redactable and to default to metadata, schema and counts rather than rows.

## 20. Identity, access control and audit

Requirements 6, 8, 13.

### 20.1 Authentication

- **Primary: federate.** OIDC / SAML 2.0 against the bank's own identity provider (Entra ID, Ping,
  ForgeRock — ask early, it has a lead time). Banks will not accept a separate user store for an
  internal application if they can avoid it, and federating removes us from the password-handling
  business entirely, which is the single largest security-review risk we can eliminate for free.
- **Fallback: local accounts**, for the pilot and for installs without an IdP. Argon2id password
  hashing, configurable password policy, TOTP MFA, account lockout with exponential backoff, forced
  rotation of the seeded admin credential on first login.
- **Sessions**: server-side, idle timeout and absolute timeout from config, secure/HttpOnly/SameSite
  cookies, invalidation on role change, and a visible session list an admin can revoke.
- **Service accounts** for scheduled runs and API integration are a distinct principal type with
  their own credentials, no interactive login, and narrow scopes.
- The local-account path must be **switchable off per install**, so a bank that federates cannot
  leave a forgotten local admin account enabled.

### 20.2 Roles

Role-based, with permissions attached to roles and roles attached to users per tenant and per
environment (a user may be an author in sandbox and a viewer in production — that is the common
case, not an edge case).

| Role | Can |
|---|---|
| `platform_admin` (vendor) | Install, upgrade, licence management, tenant provisioning. Explicitly **cannot** read tenant application data — see 20.5. |
| `tenant_admin` | Users, roles, connections, environments, non-regulatory configuration |
| `strategy_author` (maker) | Create and edit strategies, mappings and scenarios in sandbox/test; submit for approval; run simulations and the optimiser |
| `strategy_approver` (checker) | Review, approve or reject submitted versions; publish to production |
| `business_user` | Run simulations and the optimiser against approved strategies; read all results; export |
| `risk_analyst` | As business user, plus model training, support diagnostics and validation pages |
| `auditor` | Read-only across everything including the audit log; no mutation of any kind |

Roles are seeded from config and are themselves editable by `tenant_admin` (custom roles as
permission sets) — a bank will have its own names for these, and hard-coding seven strings is the
kind of small rigidity that generates six weeks of change requests.

### 20.3 Maker-checker

- Any change to a strategy, rule parameter, segmentation definition, constraint, model binding or
  data mapping creates a **new version in `draft`**, never an in-place edit.
- Promotion path: `draft` → `pending_approval` → `approved` → `published`. Rejection returns it to
  `draft` with a mandatory comment.
- **Self-approval is blocked** and the attempt is logged. Configurable per tenant only in the sense
  that a tenant may require *two* checkers; it may never be configured down to zero.
- Publishing to `production` requires the `approved` state plus the `strategy_approver` role plus an
  explicit confirmation carrying a change reference (the bank's own change ticket).
- Emergency rollback (23.4) is the one action allowed to bypass forward approval — it can only
  restore an already-approved version, and it raises a high-priority audit event.

### 20.4 Audit trail

Requirement 13: full audit of who changed what and when.

- **Append-only.** No update, no delete, enforced by database grants, not by convention.
- **Hash-chained**: each record carries the hash of the previous record for its tenant, so tampering
  is detectable. A daily digest is written to the system log the bank already collects.
- Every record: `timestamp_utc`, `tenant_id`, `actor` (user, service account or `system`), `role
  used`, `source_ip`, `session_id`, `action`, `object_type`, `object_id`, `version_before`,
  `version_after`, `config_hash_before`, `config_hash_after`, `outcome`, `reason`/`comment`.
- Audited events at minimum: authentication (success and failure), authorisation denials, every
  configuration and strategy version transition, every publish and rollback, every optimiser and
  simulation run (with `run_id`, so the audit log and the result set join), every export, every
  user/role change, every connection or credential change, every licence state transition (21.6),
  and every data-source refresh.
- **Retention** from config, default seven years, with an export-before-purge job. Banks will have
  their own retention policy; make it a number, not a code change.
- The audit log is **queryable in the UI** by the `auditor` role, filterable by actor, object, date
  and action, and exportable. An audit trail nobody can read is a compliance checkbox, not a control.

### 20.5 Vendor access

State this explicitly in the contract and implement it: **we do not have standing access to client
application data.** Vendor `platform_admin` permissions cover installation, licensing and upgrade,
not data. Support access to a client environment is time-boxed, granted by the client, logged as a
first-class audit event, and visible to them in the same audit UI. For a client relationship where
trust is already the concern (Section 21), being able to demonstrate this is worth more than it
costs.

## 21. Licensing and entitlement enforcement

Requirement 7.

### 21.1 The requirement, restated

The commercial need is legitimate and ordinary: the product is sold on a subscription, and it must
stop working if the subscription is not paid. Every enterprise software vendor does this. The stated
context — limited practical recourse in a cross-border dispute, and reputational exposure that would
hurt the smaller client base — makes it more important here, not less.

**One engineering concern, stated once.** Build this as a *disclosed, contractual licence expiry*,
not as a covert kill switch. The distinction is not decoration:

- A licence term written into the contract and the SOW, with the expiry behaviour described in
  writing and shown in the product, is a normal commercial control. It is defensible to the bank's
  security review, defensible in a dispute, and it is the thing the client's procurement team
  already expects to find.
- An undisclosed remote kill switch inside a bank's estate is a different object. If it is
  discovered during the bank's security review — and a bank reviewing on-premise software will look
  for exactly this — the deal ends and the finding travels. If it fires unannounced, the reputational
  damage is the same one the requirement exists to avoid, and it accrues to us.

So: build the enforcement to be strong, automatic, offline-capable and hard to bypass, and make it
**loudly visible in the product and in the contract from day one**. Strength and disclosure are not
in tension; disclosure is what makes the strength enforceable.

### 21.2 What it must never do

Non-negotiable, and worth writing into the contract as reassurance because it costs us nothing:

- **Never delete, corrupt, encrypt or withhold the client's own data.** Not their applications, not
  their strategies, not their audit log. Data destruction converts a payment dispute into a criminal
  and regulatory matter, in their jurisdiction, and it is the one action that guarantees we lose.
- **Never exfiltrate or transmit client data**, under any condition, as leverage or otherwise.
- **Never fire without warning.** See the ladder in 21.5.
- **Never touch anything outside our own application.** No changes to their database beyond our
  schema, no host-level action, no interference with any other system.
- **Never sit in a live customer-facing decisioning path without a documented fail-open.** Today the
  product is an offline strategy-design tool and a hard stop is a business inconvenience. If a later
  domain pack puts it in the real-time approval path (Section 29), a licence lapse that declines
  live applicants is consumer harm and a SAMA-reportable incident. The licence check for any
  real-time decision path **fails open and alerts**, and enforcement happens on the design-time
  surfaces instead.

### 21.3 Mechanism: offline signed licence

The bank's environment will have no outbound internet (16.2), so an online activation server is not
available as the primary mechanism.

- **Licence file**, issued by us, Ed25519-signed with a private key that never leaves our HSM or
  key store. The public key is embedded in the build.
- Payload: `licence_id`, `tenant_id`, `install_fingerprint`, `issued_at`, `valid_from`,
  `valid_until`, `grace_days`, `entitlements` (feature flags and limits — domain packs, user seats,
  environments, row limits), `support_tier`, `issuer`, `signature`.
- **Install fingerprint** binds the licence to the deployment (a stable derivation from the
  install's provisioning identity — not something that churns on a container restart, or the client
  will be locked out by their own Kubernetes and it will be our fault at 2am). Fingerprint mismatch
  is a **warning plus audit event**, not an immediate lock; legitimate DR failover must not brick
  the install.
- **Verification** at startup, on a configurable timer, and before any privileged operation
  (publishing a strategy, running the optimiser, adding a user). Verification failure is loud and
  specific: which check failed, what to do, who to contact.
- **Anti-rollback**: persist a monotonic high-water mark of the highest timestamp ever observed, in
  a signed record inside the database *and* on disk. A clock set backwards is detected and treated
  as expired-with-grace, with an audit event. This is the single most common bypass attempt and it
  is cheap to close.
- **Renewal is a file drop**: the client sends payment, we send a new licence file, an admin uploads
  it on the licence page. No internet, no phone call, no engineer on site. Make this path pleasant —
  friction in renewal costs more in goodwill than it gains in leverage.
- **Optional heartbeat** where a client permits egress: a periodic signed check-in that can shorten
  the effective term. Design it so its absence degrades to the offline path rather than failing.

### 21.4 Entitlements

The licence carries feature flags, and `RunContext.entitlements` (18.2) carries them into the
engine. This makes the same mechanism serve tiering and upsell, not just enforcement: domain packs,
optimiser access, champion/challenger, API integration, user seat count, concurrent environments and
row-volume ceilings are all entitlements. A feature that is not entitled is **visible but disabled
with an explanatory message**, never hidden — hiding it forfeits the upsell.

### 21.5 Enforcement ladder

Graduated, visible at every step, and reversible the instant a valid licence is installed.

| State | Trigger | Behaviour |
|---|---|---|
| `active` | Valid, > 30 days remaining | Normal. Expiry date on the licence page. |
| `expiring` | ≤ 30 days | Persistent banner for all users, escalating at 30 / 14 / 7 / 3 / 1 days. Email or notification to `tenant_admin` and to our account contact. |
| `grace` | Past `valid_until`, within `grace_days` (default 14) | **Full functionality.** Prominent non-dismissible banner with the date function will be restricted. Admin notified daily. |
| `restricted` | Past grace | **Read-only.** Existing strategies, results, audit log and data remain viewable and **exportable**. Blocked: new simulations, optimiser runs, publishing, user administration, data refresh. Full-screen explanation with renewal contact on every page. |
| `suspended` | Configurable, default 90 days past grace, or on contract termination | Login restricted to `tenant_admin` and `auditor`, for export and wind-down only. Data remains intact and retrievable. |

Two deliberate choices: **export is never blocked**, because withholding a client's own data is both
the legally dangerous act and the one that turns a payment dispute into a public fight; and
**restriction is reversible**, with a valid licence restoring full function immediately and no
re-provisioning.

### 21.6 Transparency requirements

- A **Licence page** in the product, visible to `tenant_admin` and `auditor`: state, term, entitled
  features, seat usage, days remaining, the full enforcement ladder above as text, and the renewal
  contact. No user should ever be surprised by this.
- Every licence state transition is an **audit event** (20.4).
- The contract and SOW carry the same ladder verbatim, along with the 21.2 guarantees. Ask the
  client's counsel to acknowledge the enforcement clause specifically.

### 21.7 The measures that will actually protect the business

Worth recording in the requirements document because the engineering is the weaker half of this
problem. A determined client with our binaries on their own hardware can eventually bypass any
client-side check; obfuscation raises the cost, it does not close the door (30.2). What actually
protects the revenue:

- **Payment structure**: substantial advance, milestone billing tied to delivery gates, and annual
  or quarterly licences issued *only on receipt of payment*, so the default state is expiring rather
  than running. A licence you must actively renew is worth more than any enforcement code.
- **Contract**: Saudi or neutral (DIFC/LCIA) governing law and arbitration seat rather than a court
  neither party will use, an IP clause that survives termination, and the licence-enforcement clause
  acknowledged explicitly.
- **Operational dependency**: the things only we can do — model recalibration, new domain packs,
  regulatory updates, support — are worth more than the running binary and cannot be copied with it.
- **A local partner or registered entity** in the Kingdom, if the relationship grows. It changes the
  enforcement calculus more than any of the above.

These are business decisions, not engineering ones, but the engineering should be built to support
them: short licence terms, clean renewal, and a hard technical dependency on something we hold.

## 22. Data and API integration

Requirements 4 and 11: integrated with the client's database, and with multiple databases and APIs,
all configurable.

### 22.1 Adapter interface

One interface, many implementations, selected by configuration. No engine code changes when a new
source is added.

```python
class DataSource(Protocol):
    def describe(self) -> SourceSchema: ...          # columns, types, row estimate
    def health(self) -> HealthStatus: ...            # reachable, latency, last error
    def read(self, query_spec: QuerySpec, ctx: RunContext) -> pd.DataFrame: ...
    def capabilities(self) -> set[str]:              # {"pushdown_filter", "incremental", ...}
```

Implementations for T2 onward, in priority order: **Oracle** (the likely client target — `oracledb`
thin mode to avoid an Instant Client dependency in their build pipeline), **PostgreSQL**,
**MS SQL Server**, **file drop** (Parquet/CSV/fixed-width on a watched path — the fallback every
bank can do in a week when database access takes three months), **REST/JSON API**, and
**Snowflake/BigQuery** for cloud-hosted clients. Part A's Parquet loader becomes the file adapter.

Each adapter declares its capabilities so the platform can push filters down where supported and
fall back where not, rather than pulling a million rows and filtering in pandas.

### 22.2 Connection registry

- Connections are **per-tenant configuration**, created and tested in the UI by `tenant_admin`,
  version-controlled like everything else (Section 23), with a **Test connection** button that
  reports latency, row estimate and schema.
- **Credentials never live in configuration.** Config holds a reference; the secret resolves at
  runtime from a secret provider adapter: Oracle Wallet, HashiCorp Vault, Azure Key Vault, OCI
  Vault, Kubernetes secrets, or an encrypted local store for small installs. A password in
  `config.yaml` is the finding that ends a bank security review.
- Read-only database credentials by default. We have no business writing to their core systems, and
  saying so early removes an obstacle.
- Every connection use is audited (20.4) and rate-limited.

### 22.3 Field mapping layer (the part that decides whether integration is a week or a quarter)

The engine expects the canonical schema in Section 5.1. No client will have those column names.
Mapping must be declarative configuration, never code.

```yaml
mapping:
  source: core_los_oracle
  query: "SELECT * FROM RISK.V_APPLICATIONS_HIST WHERE APP_DT >= :from_dt"
  fields:
    application_id:     {from: APPL_REF_NO}
    app_date:           {from: APP_DT, type: date, format: "YYYY-MM-DD"}
    bureau_score:       {from: SIMAH_SCORE, null_values: [0, -1, 9999]}
    employment_type:    {from: EMP_CAT, value_map: {GOV: salaried, PRIV: salaried,
                                                    SELF: self_employed, "*": other}}
    monthly_income:     {from: NET_SAL_SAR, currency: SAR}
    foir:               {derive: "(EXIST_OBLIG + PROP_INSTALMENT) / NET_SAL_SAR"}
    max_dpd_12m:        {from: WORST_DPD_12M, bucket: [0, 30, 60, 90]}
    hist_decision:      {from: FINAL_DECN, value_map: {A: approve, R: decline, "*": decline}}
    bad_flag:           {from: DPD90_12M_FLAG, type: int8, only_where: "booked"}
```

Required around it:

- **A profiling and validation step that runs before anything else**, producing a data-readiness
  report: per canonical field, the source column, fill rate, distinct values, range, type
  conformance, unmapped source values that fell through a `"*"` catch-all, and rows failing schema
  validation. Show it to the client. On every real integration this report is where the project
  actually gets done — it surfaces "your `FINAL_DECN` has five values, not two" on day one instead
  of week six.
- **Derived fields are a restricted expression language**, not `eval`. Arithmetic, comparison, null
  handling, a small function set. It must be safe to run on data we do not control, and it must be
  the same language everywhere so a mapping is reviewable by a risk analyst, not only by us.
- **Mapping is versioned and maker-checked** like any other configuration (Section 23). A silent
  change to a mapping changes every historical comparison.
- **Unmapped required fields fail loudly at validation**, listing exactly what is missing. Part A's
  discipline about silent wrongness (12.1) applies with more force here: a mis-mapped `bad_flag` is
  an entire product giving confident wrong answers.

### 22.4 API integration

Same adapter pattern for outbound calls: bureau enrichment (SIMAH), income verification (GOSI),
identity (Absher/Yakeen), external scoring services (25.2), and decision callbacks. Each declares
auth method, endpoints, timeouts, retry policy with backoff, circuit breaker, and **a response
mapping using the same field-mapping language as 22.3**. Every call is logged with latency and
outcome and feeds the monitoring in Section 28. An API that is down must produce a labelled,
visible degradation — never a silently substituted default, which in this product would be a
silently substituted *credit decision*.

### 22.5 Dataset snapshots

A run reads a **pinned dataset version**, not "whatever the table holds now". Each ingest creates a
snapshot with an id, row count, source query, extraction timestamp, and a content hash. Results
reference it (18.2). Without this, the Section 10 optimiser's determinism guarantee is void the
moment the data is live, and "the numbers changed and we do not know why" becomes the most common
support ticket.

## 23. Configuration lifecycle: versioning, comparison, rollback, promotion

Requirements 14, 15, 16.

### 23.1 Everything is a versioned artefact

Strategies, rule parameters, segmentation definitions, constraints, mappings, connections, model
bindings, thresholds and UI defaults. Each version is **immutable** and carries: `version_id`,
`tenant_id`, `artefact_type`, `parent_version_id`, `author`, `created_at`, `status`, `comment`,
`config_schema_version`, `content_hash`, and the content itself.

- **Nothing is edited in place.** An edit produces a child version. History is never rewritten —
  a bank's model-governance function will ask to see the state of the strategy on a given date, and
  the answer has to be a lookup, not an archaeology exercise.
- Part A's `strategy_io.py` (10.5) is the serialisation format; this section is the store around it.
  The round-trip guarantee in 10.5 becomes the load path for every stored version.

### 23.2 Comparison

A structured diff between any two versions of the same artefact: rules added, removed, parameters
changed with old and new values, overrides and exclusions added or dropped. Rendered side by side,
not as a text diff of JSON — the reader is a credit risk manager, not an engineer.

**Diff the impact, not just the text.** The valuable comparison is "what does this change do": run
both versions through `simulate()` on the same pinned dataset and show approval rate, blended bad
rate, swap-ins and swap-outs side by side, with the same provenance labelling Part A requires. The
engine already computes exactly this; the platform's job is to make it one click from the diff view.

### 23.3 Environments and promotion

Requirement 15: sandbox → test → production.

| Environment | Purpose | Data | Who |
|---|---|---|---|
| `sandbox` | Free experimentation | Snapshot or sample | `strategy_author` |
| `test` | Validation against a full agreed dataset, sign-off | Full pinned snapshot | author + approver |
| `production` | The live published strategy, and the baseline everything is measured against | Live pinned snapshots | `strategy_approver` publishes |

- Promotion moves an **artefact version**, not a copy — the same `version_id` is published to the
  next environment, so "what is in production" is answerable exactly and the test evidence attaches
  to the same object.
- Promotion to production requires `approved` status, the approver role, and a change reference
  (20.3).
- **Environment-specific overrides are explicit and listed at promotion** (a test connection string
  is legitimately different; a threshold is not). Anything overridden is shown in the promotion
  screen and recorded in the audit event, because an untracked environment difference is how a
  strategy behaves differently in production than in test.

### 23.4 Rollback

- One action restores any previously **approved** version. It is implemented as publishing that
  version again — forward-only history, never a deletion.
- The current state is captured before rollback so the rollback is itself reversible.
- High-priority audit event with a mandatory reason (20.4).
- Target: rollback completes in under a minute without a restart. If it needs a deployment, it is
  not a rollback.

### 23.5 Configuration is separated from the engine

Requirement 16, and the architectural rule that makes Section 24 possible:

- **No tenant-specific value lives in code or in a file inside the engine package.** Part A's
  `config.yaml` becomes the *product default layer* only (24.3). Tenant configuration lives in the
  tenant's database.
- The engine reads configuration exclusively through `RunContext.config` (18.2).
- A test must load a tenant configuration, upgrade the engine package, and assert the resolved
  configuration is byte-identical. That test is the contract behind requirement 10.

## 24. Upgrades and patching

Requirement 10: patches integrate without impacting customer configuration.

### 24.1 Versioning

Semantic versioning on the engine package and an independent `config_schema_version` on the
configuration format. A patch release may never change the configuration schema; a minor release may
add optional keys with defaults; only a major release may remove or repurpose a key, and it must
ship a migration.

### 24.2 Migrations

- Forward-only, idempotent, individually reversible where possible, each one a numbered script
  covering both database schema and configuration content.
- **Dry-run mode is mandatory and is what the client actually runs first**: report what would
  change, per tenant, per artefact, with counts, and fail the upgrade on any unmapped case rather
  than guessing.
- Migrations operate by creating **new versions of configuration artefacts** (23.1), so the
  pre-upgrade configuration remains intact and inspectable, and a migration can be rolled back by
  republishing the prior version.
- Every migration is audited.

### 24.3 Layered configuration resolution

Three layers, resolved deepest-first into the immutable `ResolvedConfig` in the `RunContext`:

```
  product defaults        shipped with the engine, replaced wholesale on upgrade
  tenant baseline         the client's configuration — NEVER touched by an upgrade
  environment override    sandbox/test/production deltas, explicit and listed (23.3)
```

An upgrade replaces layer 1 and nothing else. A new product default appears only where the tenant
has not set a value. **The resolved configuration must be inspectable in the UI with each value's
originating layer shown**, because "why is this threshold 0.035 when I set it to 0.04" is otherwise
an unanswerable support call.

### 24.4 Upgrade process

- Blue/green or rolling where the client's platform allows; a documented maintenance window where it
  does not. Database migrations run before the new version serves traffic.
- **Automatic pre-upgrade backup** of configuration and audit tables, with a tested restore.
- **Post-upgrade regression gate**: re-run a stored set of the tenant's own saved scenarios against
  the same pinned dataset snapshot and compare headline numbers to the values recorded before the
  upgrade. Differences are reported, and any difference the release notes did not predict blocks the
  upgrade. This is the strongest form of requirement 10 and the one a bank will ask for by name: it
  proves the patch did not move their numbers.
- Release notes per version listing behaviour changes, new configuration keys and their defaults,
  and any migration.

## 25. Open modelling layer

Requirement 18: support our models as well as external scorecards, ML models and APIs.

### 25.1 Interface

Part A's `RiskModel` (Section 15) generalises to a provider interface. The **provenance and support
discipline of Sections 6 and 9.2 is part of the interface, not an implementation detail** — this is
the whole point, and the easiest thing to lose when a third-party model arrives.

```python
class ScoreProvider(Protocol):
    def metadata(self) -> ModelMetadata:              # id, version, owner, trained_on,
                                                      # target definition, performance window
    def predict(self, df: pd.DataFrame, ctx: RunContext) -> pd.Series:   # NaN outside support
    def support_mask(self, df: pd.DataFrame) -> pd.Series: ...
    def support_summary(self) -> pd.DataFrame: ...
    def cell_support(self, df: pd.DataFrame) -> pd.Series: ...
    def explain(self, df: pd.DataFrame) -> pd.DataFrame: ...   # per-row contributions
```

### 25.2 Implementations

- **Built-in logistic regression** — Part A Section 9, unchanged. The default and the reference.
- **Imported scorecard** — PMML, or a declarative points-based scorecard table (banks have these and
  will want their existing one used; a points table is also the easiest thing in the world to get
  wrong in translation, so require a validation set with expected scores and assert agreement).
- **Serialised ML model** — ONNX preferred over pickle (pickle from a client is arbitrary code
  execution; if pickle must be supported, it loads in a sandboxed worker with no network).
- **External scoring API** — the bank's own model service. Batched, with timeout, retry and circuit
  breaker (22.4).
- **Bureau score used directly** — the degenerate case, and worth supporting explicitly because it
  is where several clients will start.

### 25.3 Support and provenance for external models

A third-party model usually cannot declare its own training support. Do not let that quietly
dissolve the `NOT_MODELLED` discipline, which is the product's central claim:

- A provider that cannot supply `support_mask` must be given one **derived from a declared
  reference population** the client supplies (the model's development sample, or an agreed booked
  population), using the same marginal and joint rules as Section 9.2.
- If no reference population is available, everything that provider scores is labelled with a fifth
  provenance value, **`EXTERNAL_UNVERIFIED`**, and the UI states that the product cannot vouch for
  the range in which that model is entitled to speak. Add it to the Section 6 table; it must never
  be silently mapped onto `PREDICTED`.
- Model metadata (target definition, performance window, development sample, date) is displayed
  beside every result the model produced. A PD trained on a 6-month window and a bad-rate constraint
  defined over 12 months is a mismatch the product should surface, not absorb.

### 25.4 Model registry

Versioned model artefacts per tenant (19.2), bound to strategies by reference so a strategy version
pins a model version. Champion/challenger applies to models as well as strategies (Section 27).
Performance monitoring per model version (Section 28). Retraining is an explicit, audited,
maker-checked action, never automatic — a model that silently retrains itself is unexplainable to a
regulator, and explainability is what is being sold.

## 26. Explainability of recommendations

Requirement 17. Part A already does the substance of this in Sections 10.2 and 10.3; Part B makes
it a first-class output object rather than a screen layout.

### 26.1 Structured explanation

Every optimiser recommendation, and every rejected candidate, returns an `Explanation`:

- **What** — the change, as a human-readable rule ("Approve SIMAH score 680–699 AND DBR ≤ 35% AND
  salaried").
- **Why this one** — its rank, its inferred bad rate, and what it was ranked against.
- **Expected impact** — incremental approvals, blended bad rate before and after, the change in each
  constrained metric, with a confidence interval where one exists.
- **What it rests on** — provenance split (Section 6), joint-support count and THIN flag (9.2),
  inferred share, and the sensitivity strip and breakeven penalty (9.3).
- **Which constraint drove it** — for an accepted segment, the remaining headroom after adding it;
  for a rejected one, the constraint it breached and by how much; for the run as a whole, the
  binding constraint (10.2).
- **The counterfactual** — what would have been added had the constraint been *x* instead. A credit
  committee's first question is always "and if our appetite were 4%?", and the greedy already has
  the information to answer it.

### 26.2 Decision memo export

A single export — PDF and JSON — containing the recommendation, the explanation, the candidate
funnel, the provenance breakdown, the sensitivity analysis, the data snapshot id, the model version,
the configuration version, and the run id. This is the artefact the bank's credit committee and
model-governance function sign. Selling into a regulated lender, the document is not a nice-to-have
around the product; it is frequently the deliverable.

### 26.3 Honesty carries through

Every warning Part A requires on screen — selection bias in the near-cutoff anchor (9.4), the
THIN-cell share (10.2), the `NOT_MODELLED` exclusion (Section 6), the model-basis baseline caveat
(6.1) — appears in the exported memo too, as text, at the same prominence. A caveat that survives
only on the screen and not in the document that gets circulated is a caveat that does not exist.

## 27. Champion/challenger and experimentation

Requirement 19.

- **Assignment is deterministic and reproducible**: `hash(subject_id + experiment_salt) % 10000`
  against configured allocation bands. The same applicant always lands in the same arm, assignment
  is recomputable months later from the audit log, and there is no random state to lose.
- **Design**: one champion, one or more challengers, an optional holdout, allocation percentages,
  an eligible population filter, start and end dates, and a declared primary metric with a target
  effect size. The UI computes the **sample size and expected time to read-out** from the current
  volumes and the outcome window before the experiment starts — the most common failure in
  credit experimentation is an arm that can never reach significance, and it is knowable on day one.
- **Guardrails**: automatic suspension if a challenger breaches a hard constraint (a regulatory rule,
  16.3, or a configured bad-rate ceiling) on observed data. Suspension is an alert and an audit
  event, and it is reversible only by an approver.
- **Measurement**: expected versus actual per arm, by vintage, for approval rate, decline mix, and —
  as outcomes mature — bad rate. Show the **maturity of the outcome window explicitly**: a 3-month
  read on a 12-month bad definition is not a result, and Part A's "everything is fully seasoned"
  assumption (5.1) does not survive contact with a live experiment. This is the honest counterpart
  to the provenance work: `OBSERVED_IMMATURE` is its own state.
- **Feedback loop**: challenger performance feeds the next optimisation cycle as observed data,
  which is the only mechanism in the whole product that genuinely reduces reliance on inference.
  When a challenger has matured, its approvals below the old cutoff are `OBSERVED`, and the
  conservatism penalty for that region can be measured rather than assumed (9.4).
- **Promotion and rollback**: promoting a challenger to champion is a strategy publish (23.3) with
  maker-checker; rolling back is 23.4. No separate mechanism.
- **No peeking without saying so**: interim results are shown with an explicit warning that the
  experiment has not reached its planned read-out, and the planned read-out date beside them.

## 28. Monitoring

Requirement 20.

### 28.1 Data quality

Per ingest, per field: fill rate, range conformance, type conformance, distinct-value drift,
unmapped values hitting a catch-all (22.3), duplicate keys, and row-count deviation from the
trailing average. Compared against the **baseline snapshot** the current strategy was designed on.
Thresholds in config; breaches alert and are visible on the run before anyone reads the numbers.

### 28.2 Drift

PSI/CSI per feature and on the score distribution, against the model's development sample and
against the baseline snapshot. Population stability by segment, using the Section 10.2.2 dimensions,
so drift is reported in the same vocabulary as the recommendations.

### 28.3 Strategy and model performance

Approval rate, decline-reason mix, override rate, segment volumes — tracked over time against the
levels the published strategy expected. Model AUC, calibration by decile and actual-versus-predicted
bad rate by vintage as outcomes mature, per model version. **Alert when observed diverges from
expected beyond a configured tolerance**, which is the operational form of the model-basis-baseline
check in Section 6.1.

### 28.4 Operational

Adapter health, API latency and failure rates, circuit-breaker state, job and run status with
durations, queue depth, licence state (21.5), login failures and authorisation denials.

### 28.5 Delivery

- In-product dashboard, plus export to whatever the bank already runs. **Assume no internet**: syslog
  / rsyslog, SNMP traps, Prometheus scrape on an internal endpoint, SMTP to an internal relay. Do not
  build for a hosted observability SaaS.
- **Structured JSON logging** with `run_id`, `tenant_id`, `actor` and `correlation_id` on every line,
  and **no personal data in logs** (PDPL, 16.2). Log the row count, not the rows.
- A **redactable diagnostic bundle** the client can inspect before sending: schema, counts,
  configuration hashes, versions, recent errors — metadata by default, never application rows (19.3).

## 29. Generic decision platform

Requirements 21 and 22 — architecturally the most consequential items on the list, and the ones that
decide whether this is a product or a tool.

### 29.1 The generalisation

The engine currently assumes: a **subject** that is a loan application, an **action set** that is
binary approve/decline, an **outcome** that is 90+ DPD within 12 months, and a **metric** named
`bad_rate`. Three of those four are already partly configurable (rules, segmentation and constraints
all come from config). The binary action set is not, and it is the one that blocks every other
domain.

Generalise to:

```
  Population  →  Current strategy  →  Opportunity  →  Objective  →  Constraints
             →  Alternatives  →  Simulate  →  Optimise  →  Explain
             →  Champion/Challenger  →  Measure  →  Learn
```

Every stage stays identical across domains. Only the **domain pack** changes.

### 29.2 Domain pack

A declarative bundle, config plus a small number of registered metric functions, containing no
engine logic:

```yaml
domain: originations
subject:
  entity: application
  id_field: application_id
  population: {source: core_los_oracle, mapping: originations_v3}
actions:
  type: categorical
  values: [approve, decline]
  default: decline
  reversible: false
outcome:
  definition: "max_dpd >= 90 within 12 months of booking"
  field: bad_flag
  window_months: 12
  observed_for: "action == approve"        # the reject-inference problem, declared
metrics:
  - {name: bad_rate, fn: blended_bad_rate, provenance_aware: true}
  - {name: approval_rate, fn: action_share, params: {action: approve}}
objective: {maximise: approval_rate}
constraints: [{name: bad_rate, operator: "<=", threshold: 0.035}]
segmentation: [...]                         # as Section 10.2.2
```

Other packs, none of which require an engine change:

| Domain | Subject | Actions | Outcome | Typical constraint |
|---|---|---|---|---|
| Existing book | Customer-account | increase / hold / decrease limit | Bad rate, utilisation, attrition | Bad rate, exposure growth |
| Collections | Delinquent account | call / SMS / field / settle / legal / no action | Cure or roll rate | Cost per account, capacity |
| Limits | Account | limit amount (**continuous**) | Bad rate, utilisation | Exposure, loss |
| Pricing | Application or account | rate band (**ordered**) | Bad rate, take-up, margin | Margin floor, competitiveness, regulatory cap |

### 29.3 What must change in the engine

Named specifically, because each is a small change now and a rewrite later:

1. **`decision` becomes `action`**, drawn from the domain's action set. The binary case stays the
   default and Part A's semantics are preserved exactly for it.
2. **Rule semantics generalise from approve/decline to action eligibility**: a rule constrains which
   actions a subject is eligible for. Mandatory and regulatory rules (16.3) remove actions from the
   eligible set and can never add one back.
3. **Overrides and exclusions become action assignments** — Part A's `SegmentOverride` (decline →
   approve) and `SegmentExclusion` (approve → decline) are the binary special case of "assign action
   A to this segment". Preserve the directional safety properties: an assignment that can only
   improve, and an assignment that can only restrict, remain distinct and separately governed.
4. **Metrics are registered functions** keyed by name from config (10.2.1 already specifies this;
   honour it, and make an unimplemented metric raise).
5. **The objective becomes explicit**, rather than "maximise approvals" being implicit in the
   greedy's ordering. Ascending-inferred-risk ordering is the right heuristic for
   *maximise-approvals-subject-to-bad-rate*; it is the wrong one for maximise-margin, and a pricing
   pack that silently inherits it will produce confident nonsense.
6. **Continuous and ordered action sets need a different search** than the greedy segment-adder
   (limits, pricing). Keep the optimiser behind an interface with the greedy as implementation #1,
   so a second search strategy is an addition rather than a fork.
7. **The outcome and its observation window become declared data** — including `observed_for`, which
   is where the reject-inference problem lives. In collections, outcomes are observed for *every*
   action taken, which means the inference machinery of Sections 6 and 9 is largely unnecessary
   there, and the product should say so rather than applying a conservatism penalty to data that
   does not need one.

### 29.4 What must not change

The provenance discipline (Section 6), the support discipline (9.2), the reconciliation requirements
(10.2), the "UI computes nothing" rule (12.1) and the refusal to present inference as observation
are **domain-independent**. They are the product, and every domain pack inherits them. A new pack
that cannot state where its numbers come from does not ship.

### 29.5 Contract changes

Part A Section 15 remains binding for the originations pack. Part B extends it:

- `Rule` gains `regulatory: bool = False` (16.3).
- `Strategy` gains `domain: str = "originations"` and `model_binding: str` (25.4).
- Engine entry points take `ctx: RunContext` in place of `config: dict` (18.2).
- `ScenarioResult` gains `run_id`, `dataset_version`, `config_version_id`.
- A fifth provenance value, `EXTERNAL_UNVERIFIED`, joins the Section 6 table (25.3).
- `OBSERVED_IMMATURE` joins it as well, for live experiment arms inside their outcome window (27).

These are additive; existing code keeps working with defaults, which is the point.

## 30. Intellectual property protection

Requirement 9: configurable, but the client must not be able to replicate the platform or build a
competing one with it.

### 30.1 What is defensible

- **The engine is compiled and not shipped as readable source.** Cython or Nuitka for `core/`,
  distributed as binary wheels. No `.py` for the optimiser, the inference logic or the support
  machinery. This is genuinely worth doing: it moves copying from "read the file" to "reverse
  engineer the algorithm", which is a different order of effort.
- **Configuration is expressive but not a programming language.** The client can declare rules,
  segments, mappings, constraints and domain packs. They cannot write arbitrary logic, define new
  optimiser search strategies, or add metric functions — those are registered code (29.3). This is
  the actual line between "configurable product" and "platform they can build on", and it is a
  design decision to make now, because every escape hatch added under delivery pressure erases it.
- **Keep the highest-value IP where they cannot reach it**, to whatever extent the deployment
  allows: model development methodology, the calibration and support approach, new domain packs, and
  regulatory updates are delivered as our service, not as source in their estate.
- **Contract**: source is licensed, not sold; no reverse engineering; no derivative works; IP
  survives termination; clear ownership of anything built jointly. Source escrow, if they demand it,
  is release-on-defined-trigger (our insolvency) and not on-demand.
- **Watermarking**: embed the tenant id and licence id in generated artefacts and exports, so a
  derivative work built from our outputs is traceable.

### 30.2 What is not defensible, stated plainly

Software installed on someone else's hardware can be decompiled, and client-side licence checks can
be patched out by someone determined enough. Obfuscation raises cost; it does not prevent. The
durable protections are the ones in 21.7 — commercial structure, contract, jurisdiction and
operational dependency — plus the simple fact that the product's value is in the modelling judgment
and the ongoing work, not in the code that happens to be sitting on their disk. **Build the
technical measures because they raise the cost, and do not let them substitute for the payment
structure that actually protects the business.**

## 31. Non-functional requirements and revised acceptance criteria

### 31.1 Security

- TLS everywhere including internal hops; encryption at rest via the database and the platform's
  key management; per-tenant keys (19.2).
- No secrets in code, config, logs, error messages or exports (22.2).
- Dependency scanning, SAST and container scanning in CI, with results available to the client's
  security review. A bank will ask for a recent report and an SBOM; having one ready shortens the
  review by weeks.
- Input validation at every boundary; parameterised queries only; no `eval` in the expression
  language (22.3); pickle only in a sandboxed worker (25.2).
- Penetration test before production go-live. Budget for it — the client may require their own.
- A documented vulnerability-response SLA, because it will be a contract schedule.

### 31.2 Availability and performance

- Part A's performance requirements hold per run (1M rows: rule engine < 2s, simulation < 3s,
  optimiser ~4s) and must hold **under concurrency** — the engine is stateless (18.1), so scale
  horizontally and run heavy jobs on workers rather than in the request path.
- Long-running runs are asynchronous jobs with progress, cancellation and a result that persists
  past the session. A four-second optimiser on a demo laptop is a four-minute optimiser on a bank's
  shared Oracle instance during batch hours.
- Backup and restore for configuration, audit and results, with a **tested** restore procedure and
  stated RPO/RTO.

### 31.3 Operability

- Container images and a Helm chart or Compose file; deployment documented for on-premise Kubernetes,
  plain VMs, and OCI. Air-gapped installation must work: a bundled image tarball and an offline
  dependency mirror, because `pip install` from the internet will not be available.
- Health and readiness endpoints, structured logs (28.5), a one-command smoke test the client's
  operations team can run after an upgrade.
- An installation and operations runbook written for their infrastructure team, not for us.

### 31.4 Localisation and demo data

- Arabic/RTL UI, Hijri dates alongside Gregorian, SAR formatting, `Asia/Riyadh` display with UTC
  storage, UTF-8 throughout (16.2).
- **The synthetic generator is demo and test infrastructure only.** It must not be reachable in a
  client build, and no client-facing screen may ever display Indian-rupee figures or the synthetic
  population. The Validation page (10.4) already degrades to a message when `true_bad` is absent;
  extend that to the whole generator surface.
- A **Saudi-localised demo dataset** (SAR, SIMAH-shaped score, DBR, plausible employment
  categories) for sales and training, clearly labelled as synthetic on every page.

### 31.5 Acceptance criteria — Part B

Part A Section 14 continues to apply to the engine. In addition:

- No user can access any tenant's data but their own; attempted cross-tenant access is blocked at
  both application and database layers and is audited. Proven by test, per repository.
- Authentication federates to an external IdP, and the local-account path can be disabled per
  install.
- A strategy cannot reach production without a different user approving it. Self-approval is
  blocked and logged.
- The audit log is append-only, hash-chained, queryable and exportable, and it records every
  configuration change, run, export and licence transition with actor and timestamp.
- **A regulatory-flagged rule cannot be edited, relaxed or bypassed by any path, including a segment
  override and the optimiser.** Proven by test (16.3).
- An engine upgrade leaves tenant configuration byte-identical, and the post-upgrade regression gate
  reproduces every stored scenario's headline numbers (24.4).
- The client's data loads through declarative mapping with no code change, and the data-readiness
  report is produced before any result is shown (22.3).
- A licence in `restricted` state blocks new runs and publishing, permits viewing and **export**,
  and restores full function immediately when a valid licence is installed. The enforcement ladder
  is visible in-product and matches the contract (21.5, 21.6).
- Every recommendation exports a decision memo carrying the explanation, the provenance breakdown
  and every on-screen warning (26.2, 26.3).
- Adding a second domain pack requires configuration and registered metric functions only — no
  change to `core/` (29.2). Demonstrated at least once, even with a toy pack, before T4 is called
  done.
- No personal data appears in any log, export or diagnostic bundle that leaves the client's estate
  (19.3, 28.5).
