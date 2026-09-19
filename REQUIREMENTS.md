# Originations Strategy Simulator — Prototype Requirements

## 0. Instructions to the coding agent (read first)

- You are building a **demo-grade prototype**, not a production credit model. Favour correctness, clarity and explainability over sophistication.
- Work in the **phases in Section 11**. After each phase: run tests, then **stop** and print a phase summary (files changed, test results, key numbers, open issues). Do not start the next phase until told to.
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

## 2. Out of scope

- Expected loss, fraud-rate and profitability constraints. The constraint *framework* must be general (Section 10.2.1) but only `bad_rate` is implemented. Mention the others as next steps in the UI.
- Pricing, credit limits, exposure.
- Champion/Challenger execution. Export of the recommended strategy as a versioned object is **in** scope (Section 10.5); running traffic through it is not.
- Existing-book actions.
- Authentication, databases, deployment.
- Reject inference beyond (a) a single multiplicative conservatism penalty and (b) the near-cutoff override anchor in Section 9.4. No parcelling, augmentation, or bivariate models.

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
    streamlit_app.py
  tests/
    fixtures/sample.parquet   # ~500 rows, committed, used by most tests
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
- **Validate the direction before displaying it.** Also compute the naive version (same score band, any FOIR) and show the two side by side. If they disagree in sign, say so on screen — that gap *is* the mix effect, and demonstrating it is more valuable than hiding it.
- Display with the warning that **override approvals were human-selected and are therefore favourably biased within their cell** — the observed rate is a lower bound on that cell's true rate, so the implied penalty is a lower bound on the penalty you should use.
- Sanity check, not a target: within a matched cell the selection effect in the current synthetic data is large, on the order of 20%. A measured effect near zero means the comparison is still confounded, not that selection is absent. Report what you measure; do not tune towards a number.
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
  - the list of **rejected** segments with the reason, so the user can see where the appetite ran out
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
- Rank segments by **observed** bad rate, descending. Show the worst segments with count, observed bad rate and their contribution to total bads.
- Show the combined trade: declining the worst N approved segments frees bad-rate headroom; feed that headroom back into the optimiser and report the net effect — approvals lost, approvals gained, net approval rate, net blended bad rate.
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
| 4 | Streamlit UI (Section 12) | all pages work end-to-end on 1M rows |
| 5 | README, cleanup, demo script | fresh-clone setup works in under 10 minutes |

### 11.1 Headless entry points (required from Phase 2)

Phases 1–3 must be verifiable without the UI. Provide:

- `python -m src.generate_data` — builds the dataset, prints the 5.3 calibration table.
- `python -m src.risk_model` — trains, prints AUC, calibration table, coefficients, support ranges.
- `python -m src.simulate --scenario <json>` — prints a JSON result block.
- `python -m src.optimise` — prints the full JSON headline, segment list, naive comparison and sensitivity strip.

All four print machine-readable JSON to stdout (a human-readable table to stderr is fine).

## 12. UI (Streamlit)

Pages:
1. **Overview**: population size, baseline approval rate, observed bad rate, reproduction match rate (raw and excluding overrides), override counts, performance-window assumption, data provenance note.
2. **Decline waterfall**: sequential chart, override adjustment step, single-rule declines, score × FOIR heatmap.
3. **Risk model**: AUC, calibration chart, coefficients, training-support ranges and out-of-support counts, extrapolation warning, near-cutoff anchor (9.4).
4. **What-if simulator**: parameter controls, baseline vs scenario KPIs, observed / model-basis / inferred / blended split, `NOT_MODELLED` panel, swap-in breakdown, sensitivity strip.
5. **Optimiser**: constraint input, run button, headline, added-segment rules table, rejected-segment table, naive comparison chart, breakeven penalty, export button.
6. **Portfolio quality**: swap-out analysis (10.3).
7. **Validation** (synthetic only).
8. **Next steps**: static text covering Champion/Challenger (referencing the exported strategy object), additional constraints, and existing-book use cases.

Show provenance labels as visible badges or suffixes next to every bad-rate figure. Every page with a results table offers CSV/JSON download. Cache data and the model with `st.cache_data` / `st.cache_resource`. Warn when the inferred share of approvals exceeds `max_inferred_share` (config, default 0.50).

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
- Strategy export round-trips to the same headline numbers.
- The generator is deterministic for a given seed.
- The committed fixture equals a fresh rebuild from the generator, so it cannot go stale behind a passing suite.
- Editing a rule parameter that does not exist raises rather than running as a silent no-op.
- The waterfall's override adjustment step is derived from `manual_override`; a non-override disagreement raises.
- An applicant whose feature value sits in a supported bin but outside the booked range is `NOT_MODELLED`.
- **`test_leakage.py`**: scan every file in `src/` except `generate_data.py` and `validation.py` for the string `true_bad` and fail on any occurrence.

## 14. Acceptance criteria

- `python -m src.generate_data` builds the dataset and prints calibration results within the 5.3 targets.
- `pytest` passes, in under 60 seconds, without the 1M-row dataset.
- All four headless commands in 11.1 emit valid JSON.
- `streamlit run app/streamlit_app.py` runs all pages on 1M rows without errors.
- The optimiser shows more approvals than baseline, a blended bad rate within the constraint, and a targeted strategy that beats or matches the naive cutoff reduction.
- **The constraint binds**: the optimiser rejects at least one candidate segment. If it accepts everything, there is no optimisation story — report this rather than shipping it.
- Incremental approvals are between 3 and 12 percentage points of the application population.
- Every bad-rate number carries a provenance label, and no `NOT_MODELLED` population is silently folded into a headline.

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
class Strategy:
    rules: tuple             # tuple[Rule, ...] in evaluation order
    overrides: tuple = ()    # tuple[SegmentOverride, ...]

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
