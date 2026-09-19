# Originations Strategy Simulator

Answers one question for a lender, without lying about how much of the answer is known:

> *Given my current credit strategy and risk appetite, where can I change the strategy to approve
> more applicants without exceeding my bad-rate limit?*

The engine loads a historical application population (approved **and** declined), reproduces the
current approve/decline strategy, explains the decline waterfall, simulates strategy changes, and
searches for a better strategy under an explicit bad-rate constraint.

Its distinguishing property is not the optimiser. It is that **every number carries a provenance
label** — whether it was observed, predicted, inferred, or cannot be modelled at all — and that the
product refuses to present an inferred number as an observed one. See [Honesty rules](#honesty-rules).

Full specification: [REQUIREMENTS.md](REQUIREMENTS.md). Part A (Sections 0–15) is this engine;
Part B (Sections 16–31) is the platform it is being built into.

---

## Quickstart

Python 3.11+ required. From a fresh clone:

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

```bash
python -m src.generate_data
```

```bash
pytest
```

```bash
streamlit run app/streamlit_app.py
```

Cold start is a few minutes, effectively all of it `pip install`:

| Step | Time | Notes |
|---|---|---|
| `pip install -r requirements.txt` | 1–3 min | Pinned versions |
| `python -m src.generate_data` | ~3 s | Builds 1,000,000 rows into `data/` and prints the Section 5.3 calibration table |
| `pytest` | ~30 s | 123 tests. Does **not** need the 1M dataset — it builds its own |
| `streamlit run app/streamlit_app.py` | ~10 s to first page | Loads and caches the 1M dataset |

Measured on an Apple M-series laptop.

On Windows use Git Bash and `.venv/Scripts/activate`. All paths are relative and `pathlib`-based.

---

## Headless entry points

Every page in the UI reads its numbers from these same functions — the UI computes nothing
(Section 12.1). Each prints machine-readable JSON to stdout and a human-readable table to stderr,
so they compose in a shell and are the right way to verify a change.

```bash
python -m src.generate_data
```
Builds the dataset and prints the eight calibration targets with pass/fail.

```bash
python -m src.risk_model
```
Trains the PD model; prints AUC, the calibration table, coefficients, per-feature training-support
ranges and the near-cutoff inference anchor.

```bash
python -m src.simulate --scenario '{"rules": {"R5_SCORE": {"cutoff": 680}}}'
```
Simulates a strategy change. `--scenario` takes inline JSON or a file path; omit it for the
baseline. The same JSON loads and saves from the What-if page.

```bash
python -m src.optimise
```
Runs the optimiser, the naive-cutoff comparison, the swap-out analysis and the combined trade.
Prints the full headline, segment list, candidate funnel and sensitivity strip.

All four accept `--config` to point at an alternative `config.yaml`, and all but `generate_data`
accept `--data`. `ORIGSIM_DATA_PATH` overrides the dataset location for every consumer at once.

---

## What it produces

On the shipped configuration and the 1M-row synthetic dataset:

| | |
|---|---|
| Baseline approval rate | **39.86%** (398,646 approvals) |
| Baseline observed bad rate | **2.86%** `OBSERVED` |
| Strategy reproduction | **99.00%** raw, **100.00%** excluding manual overrides |
| Optimised approval rate | **51.20%** (+113,341 approvals) |
| Expected blended bad rate | **3.499%** against a 3.50% cap `OBSERVED+INFERRED` |
| Binding constraint | `bad_rate` — the appetite ran out, 17 candidate segments rejected |
| Naive comparison | Lowering the cutoff to 678 buys 474,462 approvals at the same 3.48% — the targeted strategy beats it by **37,525 approvals** |
| THIN share of incremental approvals | **94.4%** of evaluated, **92.0%** of the headline |

That last row is the point of the product. The optimiser sorts candidate segments by ascending
inferred risk, which selects preferentially for cells with the least observed evidence behind them.
94.4% of the recommended approvals sit in cells with fewer than 100 observed booked customers. The
number is shown next to the headline, not in a footnote, because a recommendation that does not
disclose this is a sales tool.

---

## Honesty rules

These are the constraints the codebase is organised around. Each exists because the opposite
behaviour produces a confident wrong answer that nobody catches.

**Provenance on every figure** (Section 6). `OBSERVED` is the actual bad flag of booked customers.
`PREDICTED` is model PD on booked customers. `INFERRED` is model PD on historical declines, times a
conservatism penalty. `NOT_MODELLED` means the applicant is outside the model's training support
and **no PD is produced at all**.

**`NOT_MODELLED` is never imputed to zero.** Those approvals count in the approval rate and are
excluded from the blended bad rate, with the exclusion stated next to the figure. A missing rate
renders as `—`, never `0.00%`.

**Support is checked jointly, not just marginally** (Section 9.2). A feature bin can hold thousands
of booked rows and still span values no booked customer has. Support therefore requires both a
dense decile bin *and* a value inside the booked min–max — without the second clause, relaxing the
enquiry limit to 12 prices ~1,400 approvals by extrapolating seventeen units past any training data,
every one of them silently scored.

**Evidence counts travel with the numbers.** `cell_support` reports how many booked customers sit
in each recommendation's segmentation cell. It never changes a decision or a PD; cells below
`min_cell_obs` are flagged THIN and shown, never suppressed.

**The model-basis baseline** (Section 6.1). Comparing an observed baseline against a blended
observed+inferred scenario mixes a real strategy effect with model bias, so every result also
reports the mean predicted PD of the baseline booked population — the like-for-like comparator.

**The near-cutoff anchor conditions on FOIR, not just score** (Section 9.4). Manual overrides give
genuine observed performance below the cutoff, but they are drawn from a marginal slice. Compared
across the whole score band the implied penalty is **1.063**; compared within matched cells it is
**0.895**. The two disagree in sign, that gap is the FOIR mix effect, and the product shows both
rather than picking the flattering one.

**`true_bad` is quarantined.** The synthetic oracle is readable only by `generate_data.py` and
`validation.py`. `tests/test_leakage.py` scans every other file in `src/` for the string and fails
on any occurrence.

**The UI computes nothing.** No page recomputes a rate inline and no page sums a table to produce a
headline. Errors surface as errors — `ReproductionError` and the unknown-rule-parameter `KeyError`
were added on purpose, and a run that swallows either is a failed build.

---

## Reading a result

Two fields decide whether a comparison between two runs is meaningful.

**`binding_constraint`** says what stopped the greedy. `bad_rate` means the strategy spent its whole
risk budget. `max_segments_added` means it ran out of rule slots with appetite still unspent. A
delta between two runs that stopped for different reasons is not a finding — the swap-out page
withholds it rather than printing it.

**`breakeven_penalty`** is the conservatism penalty at which the recommendation first breaches the
constraint. Read it together with `binding_constraint`: when the run is appetite-bound, the greedy
by construction stops just inside the cap, so breakeven lands a hair above the operating penalty
(here 1.2508 against a default of 1.25) and tells you only that the constraint binds. It carries
real information when the run is **slot-bound** and there is unspent headroom. The sensitivity
strip — the same result re-costed at penalties 1.0, 1.25, 1.5 and 2.0 — is the more useful view
either way.

---

## Layout

```
config.yaml            every business parameter; no magic numbers in code
src/
  contracts.py         the dataclasses the phases agree on (Section 15)
  config.py            the only module that reads config.yaml
  generate_data.py     synthetic generator, incl. manual overrides — may read true_bad
  loader.py            schema validation; a real dataset with these columns drops straight in
  rules.py             strategy object + vectorised rule engine, overrides and exclusions
  waterfall.py         sequential decline waterfall
  risk_model.py        PD model, marginal + joint training support, provenance, 9.4 anchor
  segments.py          config-driven segmentation and banding
  simulate.py          what-if simulation
  optimise.py          greedy optimiser, naive comparison, swap-out, combined trade
  strategy_io.py       versioned strategy export/import (JSON)
  validation.py        synthetic-oracle checks — may read true_bad
app/
  streamlit_app.py     entry point; one module per page under app/pages/
tests/                 123 tests, ~30 s, no 1M dataset required
```

## Configuration

Everything tunable lives in `config.yaml`: the strategy and its rule parameters, generator
distributions, calibration targets, model thresholds (`min_support_obs`, `min_cell_obs`,
`min_level_obs`, `inference_penalty`), constraints, segmentation dimensions and optimiser limits.

Two are designed to be extended without touching code:

```yaml
constraints:
  - {name: bad_rate, metric: blended_bad_rate, operator: "<=", threshold: 0.035, enabled: true}

segmentation:
  - {column: bureau_score, type: band, edges: [640, 660, 680, 700]}
  - {column: foir,         type: band, edges: [0.0, 0.35, 0.50, 0.60]}
  - {column: employment_type, type: categorical}
```

Adding expected loss or a fraud-rate constraint is a config entry plus one metric function. Adding
`enquiries_6m` as a segmentation dimension is a config entry alone. A metric named in config but
not implemented raises rather than being ignored.

## Assumptions

- **Every booked application is treated as fully seasoned** — 12 months of performance is assumed
  available for all of them, including the most recent cohort. Real data needs vintage-based
  censoring, and the Overview page states this.
- `booked == (hist_decision == approve)`.
- The dataset is synthetic and Indian-denominated (INR, CIBIL-shaped scores). It is demo and test
  infrastructure only — see REQUIREMENTS.md Section 31.4.
- If `true_bad` is absent, the Validation page degrades to a message rather than raising, so a real
  dataset with the same columns runs everything else unchanged.
