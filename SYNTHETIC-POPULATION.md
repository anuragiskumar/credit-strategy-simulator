# Synthetic client-shaped population — step 2

50,000 TWQR applicants shaped to the client's real field list, built so the client's own 227 TWQR rules decide
who is declined and why.

```bash
python -m src.client_generate --fixture
```

Writes `data/client_applications.parquet` (50,000 rows) and `tests/fixtures/client_sample.parquet`
(2,000 rows), and prints the calibration report. `--check` prints the report without writing.
All parameters are in `config_client.yaml`; there are no numbers in the code.

## The rule this is built on: derive, don't assign

The generator sets **field values only**. It never writes a decline reason, a funnel stage or an
approval. Those come from replaying the real rules in step 3.

That is not a stylistic preference. If a reason were assigned at random, moving "minimum salary
3,500 → 3,000" would change nothing, because no applicant's reason was ever connected to their
salary — and the decline-driver ranking would be noise that still looked plausible. Deriving
everything means moving a threshold genuinely moves people across it.

The same rule applies inside the generator. `employer_keyword_check` is not a stored Y/N; the
loader runs the client's 61 Arabic substring tests against a real employer name. Edit the keyword list
and the population moves with it. A test asserts exactly that.

## Three layers, so the client file can drop in

The brief requires the loader to stay separate from the engine, because real client data was
expected Tuesday. The split:

| Layer | File | Job |
| --- | --- | --- |
| Schema | [src/client_schema.py](src/client_schema.py) | the canonical applicant: 34 columns, validation, the segment dialects |
| Generator | [src/client_generate.py](src/client_generate.py) | synthetic applicants conforming to it |
| Loader | [src/client_loader.py](src/client_loader.py) | any source → canonical → each rule table's field names |

When the real file arrives, only `client_loader.map_source()` is touched:

```python
mapped = client_loader.map_source(raw_df, {"SALARY": "monthly_income"}, constants={"product": "TWQR"})
```

It raises rather than guesses — a source missing a canonical column is an error, not a silent
null that reaches the analysis.

### The segment problem this layer exists to solve

The client's files use **three different vocabularies for the same attribute**. A government employee is:

| Concept | racAndPolicies | simati_chk_IAF | yknBasicCheckValidation |
| --- | --- | --- | --- |
| Government | `ST` | `ST` | `G` |
| Semi-government | `SMG` | `SMG` | `SG` |
| Private large | `PVTL` | `PVTL` | `PL` |
| Private small | `PVTSML` | `PVTSML` | `PS` |
| Self-employed | `SE` | `Establishment` | `SE` |
| BSF priority | `PRIO` | `BSF Priority` | `BSFPB` |

`yknBasicCheckValidation` goes further: it folds **employment type and pensioner status into the
same column**. Military is `M`, a pensioner is `P` — neither of which is an employer segment.
Render a military applicant as `G` there and they escape that table's age band entirely, which
for a military applicant is 42–58 rather than 20–60. The applicant carries one canonical value;
`client_schema.to_dialect()` renders it per table. Three tests cover it.

Also worth knowing: **length of service has three names** — `monthCnt` in racAndPolicies,
`netIncome.lengthOfService` in simati, and it is implied by the age bands in ykn. The loader maps
all of them to one column.

## What each applicant carries

34 columns. Beyond the fields the rules read:

- **Sourcing** — `channel`, `source_code`, `agent_id`. No rule file records these (`sourceType`
  appears in 1 of 260 rows), but Guru's question 4 needs them, so they are application
  attributes.
- **`sector`** — Guru asked to slice the portfolio by sector. `V_SECTOR_TYPE` is declared in
  the client's bureau file and never populated, so sector cannot come from the rules either.
- **`latent_bad`** — the true outcome for **every** applicant, including those who are declined.
  No real bank has this. It exists so reject inference can later be scored against truth, and it
  is excluded from `client_schema.ENGINE_VISIBLE` so the analysis layer cannot read it.

## The four planted answers

The engine is meant to replace a human's judgement, so the only way to know it works is to hide
a known truth and check it comes back out.

| # | Planted | Verified |
| --- | --- | --- |
| 1 | The digital channel carries the weakest mix | median income 5,909 vs 9,680 branch; 22.9% no-score vs 10.9%; 17.9% bad vs 10.4% |
| 2 | Length of service does **not** predict risk, though rules decline on it | correlation with the outcome **0.0008** |
| 3 | A missing SIMAH score is the riskiest state, not a neutral one | **1.44×** the scored population's bad rate |
| 4 | Concentrated in IT, thin in finance, no government exposure | IT 34%, finance 2%, government **0** |

Plants 2 and 3 are the Kaggle notebook's two findings reproduced deliberately: employment length
was flat at 12.6–14.5% while policy demanded five years of it, and the blank-employment-length
group was the riskiest at 20.5%. Plant 2 is the correct answer to question 10 — *which rules cost
approvals without reducing risk*. Plant 1 is Guru's Alpha client, where 980 declines all came
from digital. Plant 4 is his IT-80%/finance-5% example.

Each is asserted by a test, so a future change to the generator that quietly removes one fails
the build rather than silently weakening the demo.

## Calibration: the guardrail that matters

A rule whose threshold sits outside the population **never fires**, so it drops out of the
decline-driver ranking — and a ranking with a missing rule still looks perfectly plausible. That
is the same failure mode the brief rejected random rejection reasons for.

`threshold_coverage()` checks all **61 tunable TWQR thresholds** and counts applicants on each
side. Current state: **0 thresholds with nobody on one side.** Three needed fixing during the
build, and each was a real modelling point rather than a tuning nudge:

- `<3000` on `loanAmount` is a **minimum** finance amount, not a cap. Requests scaled to income
  never went that low, so the rule was inert. Fixed by adding small-ticket requests that do not
  scale with income — someone wanting a top-up.
- Minimum length of service of 1, 3 and 6 months needed a genuine tail of recent joiners.
- The 1M and 1.5M TWQR caps needed a high-earner tail.

Seven thresholds remain thinly covered; all are band edges (`[0..14999]`, `[15000..9999999]`)
where the endpoint is a sentinel meaning "no limit", or the 1M/1.5M caps, which genuinely are
rare in personal finance. None disables a rule.

## Does the population behave like a bank's?

Marginal share caught by each headline condition, with the true bad rate of that group:

| Condition | Applicants | Share | Bad rate |
| --- | --- | --- | --- |
| SIMAH score < 600 | 15,703 | 31.4% | 25.7% |
| No SIMAH score at all | 8,190 | 16.4% | 18.6% |
| CRIF score ≤ 605 | 25,230 | 50.5% | 21.6% |
| Income < 3,500 (civilian minimum) | 7,026 | 14.1% | 21.4% |
| Age outside 20–60 | 4,051 | 8.1% | 13.1% |
| Employer keyword hit (small trader) | 8,762 | 17.5% | 15.9% |
| Length of service < 3 months | 1,158 | 2.3% | 12.4% |
| Payslip older than 2 months | 2,585 | 5.2% | 14.0% |
| Bank staff — declined outright | 211 | 0.4% | 16.6% |
| Walked away, bank too slow | 4,749 | 9.5% | 14.8% |
| **Any of: score < 600, no score, CRIF ≤ 605** | **30,027** | **60.1%** | **20.4%** |

That last line is the useful one. Guru's funnel loses 30 per 100 to hard rejects and another 30
to credit policy — **60 by that stage**, which is where this population lands. The shape was not
tuned to match; it falls out of thresholds the client actually wrote meeting a realistic applicant mix.

Population bad rate is **13.8%**, against the 13.95% the notebook arrived at on LendingClub once
a performance window was applied. The score-to-risk curve runs 50.3% bad below 500 to 2.0% above
700 — steep enough that moving a cutoff has a real trade-off, which is what the simulator needs.

## What is deliberately not here

- **No funnel stage or decline reason on any applicant.** Those are step 3's output, derived by
  replaying the rules. The schema has no `decline_reason` column and should not gain one until
  the replay writes it.
- **No booked flag or observed bad flag.** Who gets booked depends on the replay. `latent_bad`
  is the ground truth waiting to be revealed for whoever the replay approves — which is also
  what makes reject inference testable later.
- **No LendingClub data.** The notebook's *shapes* are reproduced — lognormal income, an
  elasticity below 1 from income to requested amount, a steep score-to-default curve — but none
  of its data is used, per the brief's terms-of-service warning.

## Caveats to say out loud in the demo

- **The applicants are synthetic; the numbers are illustrative.** What is real is the rules and
  the method. The brief is explicit that claiming otherwise would not be acceptable.
- The population is calibrated to make the client's thresholds bite realistically. It is **not** a
  claim about the client's actual book, which we have never seen.
- `latent_bad` gives every declined applicant a true outcome. That is a property of synthetic
  data and the reason reject inference can be *tested* here but not *solved* here.

## Open questions carried into step 3

The three from step 1 are still the blockers, and they now have teeth, because the population
will expose them:

1. **Is there an evaluation order?** 33 overlapping bands mean order changes the outcome. With
   8.1% of applicants outside 20–60, the `G`/`SG` age contradiction (20–60 vs 30–70) will hit
   real rows.
2. **Are `Decline`, `Fail` and `Exception` one pass or several?** `executionLevel` says `RAC` or
   `SIMATI`, which hints at two, but not their order.
3. **What happens when no rule matches** — approve or decline?

One new question from this step:

4. **`monthCnt` values are bare numbers** (`1`, `3`, `6`, `12`, `24`) with the operator lost in
   export. The descriptions all say "LOS", so they are almost certainly minimums, but the
   inventory has to record them as `eq`. Read as equality they almost never fire; read as
   minimums they decline 2.3% of applicants. **The client has to confirm which.**
