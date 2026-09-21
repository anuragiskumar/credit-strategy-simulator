# Engine, simulator and surfaces — steps 3 to 6

Steps 1 and 2 produced the rules and the population. This is what runs on them.

| Step | What | Module |
| --- | --- | --- |
| 3 | Rule replay, funnel, decline drivers | [src/client_replay.py](src/client_replay.py), [src/client_analysis.py](src/client_analysis.py) |
| 3 | PD model and the honesty guard | [src/client_risk.py](src/client_risk.py) |
| 4 | What-if simulation and swap sets | [src/client_simulate.py](src/client_simulate.py) |
| 4 | Goal-seek to a target approval rate | [src/client_optimise.py](src/client_optimise.py) |
| 5 | Three CxO screens | [ui/client.html](ui/client.html), [ui/client.js](ui/client.js), [ui/client_export.py](ui/client_export.py) |
| 6 | Thin LLM layer | [src/client_llm.py](src/client_llm.py), [src/client_ask.py](src/client_ask.py) |

```bash
python -m src.client_ask "which rules cost approvals without reducing risk?"
```

```bash
python -m ui.client_export && python -m ui.serve
```

Then open <http://127.0.0.1:8777/client.html>.

## Step 3 — replay

226 of the client's TWQR rules are compiled into vectorised predicates and evaluated against all
50,000 applicants. One rule cannot be evaluated: `racAndPolicies#261` needs SIMAH installment
history we do not model. It is reported by name rather than silently treated as never firing.

**Three decisions the export does not record.** The client's files do not say how the rules are
evaluated, so these live in `config_client.yaml: replay`, are printed into the fixture's `meta`,
and are shown on the screens. They are not facts about the client, and the funnel moves when they
change:

| Decision | Default here | Why it matters |
| --- | --- | --- |
| Evaluation order | table order, first match wins | 33 overlapping bands mean order changes the outcome |
| A condition on a missing value | does not match | 16.4% have no SIMAH score and 102 rules test it |
| An applicant no rule matches | approve | no column carries a default |

All three are still open questions for the client.

### The funnel

| Stage | Guru's funnel | This population |
| --- | --- | --- |
| Applied | 100 | 100 |
| After hard rejects | 70 | 80.0 |
| After credit policy | 40 | 38.4 |
| After the eligibility cut | 20 | 24.2 |
| After customers walk away | 10 | 21.9 |
| Booked | 10 | 21.9 |

The first three stages land close to the funnel Guru described, and they were not tuned to —
they fall out of the client's own thresholds meeting a realistic applicant mix.

**The last stage does not match Guru's, and that is a choice.** His funnel loses half the
remaining applicants to the bank being slow; ours loses 1,136 of the 12,076 who reach that
stage (9.4%). That figure is a **demo calibration, not an observation**: `walk_away.base_share`
in `config_client.yaml` was lowered from 0.10 to 0.0746 to give it, and it was never verified
against real data. Only the walk-away draw changes with it, so the applicants and the rules'
decisions are identical either way. Everything downstream of booking does move (the approval
rate went from 21.1% to 21.9%, and the booked book, exposure and risk model with it).

Note the last two rows are equal by construction: `left` is the count still in after a stage,
and walking away is the last stage that removes anyone, so what is left after it is what is
booked. The number who walked away is the `dropped` column, 1,136.

### Decline drivers

Ranked by **applicants declined alone** — how many an individual rule catches that no other
rule does. That is the column that answers *"what is the one thing I change?"*, because
switching off a rule that always fires alongside another buys nothing.

| Rule | Declines | Alone | Estimated bad rate if relaxed |
| --- | --- | --- | --- |
| `racAndPolicies#012` CRIF ≤ 570 and SIMAH ≤ 650 | 12,676 | 4,444 | 26.3% |
| `yknBasicCheckValidation#016` age not 20–70 | 6,643 | 3,125 | 8.5% |
| `racAndPolicies#015` employer keyword + CRIF < 626 | 5,487 | 2,078 | 14.1% |
| `simati_chk_IAF#004` minimum salary 3,500 | 5,060 | 1,624 | no estimate |

Against a booked bad rate of **8.29%**.

**The second row is the demo.** `yknBasicCheckValidation#016` is the rule step 1 flagged as
contradicting another: it caps government and semi-government employees at 30–70 while row 2
caps the same segments at 20–60. It is the second-largest decline driver in the book, it
declines 3,125 applicants nobody else catches, and those applicants are **no riskier than the
book already carries**. A contradiction found by reading the files, then priced in applicants.

### Freeing people from a rule does not book them

Switching off `racAndPolicies#012` releases 4,444 applicants from credit policy, but approvals
rise by only 3.85pp. Of those freed, 2,332 immediately hit the eligibility cut and 186 walk
away. The funnel shows this directly, and it is the sort of thing a single-number answer hides.

## Step 3 — the risk side, and what it refuses to say

A declined applicant has no repayment history. The PD model therefore trains **only on booked
applicants**, which is all a real bank has, and refuses to answer in three cases:

1. the group sits outside the score range the bank has ever booked;
2. the group is mostly applicants with no score, on a book that never funded any;
3. the group has fewer than 50 applicants.

The third was added after a test caught the engine declaring a rule "does not earn its place"
on the evidence of **ten** people. A verdict that thin is worse than silence in front of a risk
committee.

Where the engine does answer, its estimate tracks the truth closely: mean absolute error
**0.030** against the synthetic ground truth, across every rule with 100+ sole declines. The
oracle exists only because the population is synthetic; `include_oracle=True` is off by
default and never reaches a screen.

**Gini is 0.60, which is optimistic.** The synthetic risk is generated from the same features
the model reads, so the model is scoring a world it was told about. The notebook got 0.258 on
real LendingClub data. Treat 0.60 as a property of the fixture, not a claim about the method.

### The compliance guard

A rule resting on a regulatory fact is never offered as a relaxation, whatever it costs:

| Rule | Rests on |
| --- | --- |
| `racAndPolicies#099` | diplomatic service |
| `racAndPolicies#100` | politically exposed person |
| `racAndPolicies#101` | related to a PEP |
| `racAndPolicies#104` | gender |
| `simati_chk_IAF#031` | Bank staff |

Nationality and customer segment are deliberately **not** on this list. They scope a rule to a
population; the threshold inside it is still the bank's to move. Treating them as off-limits
would put 177 of 226 rules beyond the optimiser for no reason.

## Step 4 — simulator

A **lever** is one change a person can describe in a sentence: move a threshold, or switch a
rule off. `field_lever` moves every rule testing the same number at once — one lever on the
SIMAH cutoff touches 51 rules.

Three correctness properties, each of which failed at some point during the build and each of
which now has a regression test:

- **Direction awareness.** Lowering a `>=` threshold tightens a decline rule rather than
  loosening it. A move is applied only where it genuinely loosens; conditions pointing the
  other way are skipped and counted, never silently reversed.
- **One field at a time.** A rule commonly tests two scores. Patching all of a rule's
  conditions while the user asked to move one silently moved the other, which showed up as
  approvals *falling* when the user had loosened something.
- **Pass rules move with the Fail rules they mirror.** simati writes `<3500` Fail and `>=3500`
  Pass as a pair; moving one alone leaves applicants falling between them.

With those fixed, every pure relaxation produces **zero swap-outs**, which is the invariant
the tests assert.

### Editing one rule, in either direction

`threshold_lever(base, inv, rule_id, field, value_low=, value_high=)` edits one threshold of one
rule and does exactly what was asked, **tightening included**. That is deliberate: a tightening is
the only way anyone approved today is newly declined, and "would raising Minimum Income Non Saudi
to 6,000 cost us good loans?" is a question a bank asks. The lever records `direction` (loosen,
tighten, mixed) so the screen can say which way it went. `field_lever(..., allow_tighten=True)` is
the same for a field-wide move; the optimiser never sets it.

| `racAndPolicies#028` Minimum Income Non Saudi | Newly approved | Newly declined |
|---|---|---|
| 5,000 → 4,000 | 76 | 0 |
| switched off | 126 | 0 |
| 5,000 → 6,000 | 0 | 121 |

- A rule-level edit moves the Pass rule it mirrors, as `field_lever` already did.
- A locked or fixed-field rule is refused (`NotEditable`), for a person exactly as for the search.
- **Fixed:** a pure tightening reported the expected bad rate as unknown, because the swap-in group
  was empty and "no applicants" was treated as "cannot estimate". The new book is then exactly the
  loans that stay, all observed. Swap-outs are booked loans, so their bad rate is observed too
  (`swap_out_observed_bad_rate`), not predicted.

### Replaying only what changed

A rule's verdict depends only on its own conditions, so `replay(..., base=baseline.res)`
re-evaluates the overridden rules and reuses every other column. A test holds it to giving exactly
what a full replay gives. One what-if went from 0.94s to 0.06s and a 30% goal-seek from 93s to
11s, which is what makes laddering changes and a typed goal-seek target usable live.

## Step 4 — goal-seek

```
GOAL 30% approval (from 21.88%), bad-rate ceiling 11%

A  30.8%  +8.87pp   4,435 newly approved   10.63% expected bad   +2.34pp risk
   switch off racAndPolicies#012 · switch off yknBasicCheckValidation#016
   · switch off simati_chk_IAF#006

B  30.3%  +8.42pp   4,212 newly approved   10.63% expected bad   +2.34pp risk
   switch off racAndPolicies#012 · switch off yknBasicCheckValidation#016
   · switch off racAndPolicies#221
```

**Every search is bounded by a bad rate ceiling.** The brief flags the gap nobody raised on
the call: "maximise approval rate" alone is solved by approving everyone. Neither option
above crosses the ceiling; one that did would be flagged and never ranked first, which the
simulator tests assert.

Two further refusals: an option whose swap-ins cannot be priced is ranked **last**, because a
cheap-looking option we cannot price is not a cheap option; and a regulatory rule is never a
candidate.

When the target is reachable, options are ranked by **risk cost**. When it is not, they are
ranked by how close they get — ranking those by risk cost answers a question nobody asked, and
returned a *worse* approval rate than a lower target did until it was fixed.

The output is a ranked shortlist for a human, not a proof of optimality. Beam search over
single changes, width 3, depth 3.

The target and the ceiling are the person's to set (`goal_seek(..., ceiling=, frozen=)`); `frozen`
names rules they will not have touched. The fixture still precomputes 25% and 30% for the
no-engine fallback: 30% is Guru's example from the call, 25% was a midpoint chosen during the build.

## Step 5 — three CxO screens

<http://127.0.0.1:8777/client.html> — Portfolio, Decline drivers, Simulator.

They reuse the existing prototype's design system, now extracted to `ui/tokens.css` and shared
by both pages, so there is one source of truth rather than a copy.

**Colour encodes provenance and nothing else**, which is the existing rule and matters more
here than anywhere: the screens mix counted figures with inferred ones and with figures the
engine refuses to give.

| Tag | Means |
| --- | --- |
| `OBSERVED` | counted from the replay — applicants, declines, booked performance |
| `PREDICTED` | the PD model inside the population it was trained on |
| `INFERRED` | reject inference — applicants the bank has never seen repay |
| `NOT_MODELLED` | refused, drawn hatched so an absence never reads as a number |

**The UI computes nothing.** Every figure comes from `ui/client_export.py`, which calls the same
functions the CLIs and the tests call. A test asserts the page never divides one fixture field
by another, and another asserts the fixture supplies every rate the screens display.

Three fixes to the existing prototype came out of this:

- **Neither page declared a viewport**, so the ~60 lines of responsive CSS in `tokens.css`
  never applied on a phone. One line, both pages.
- **The rail toggle used the wrong class** (`open` where the stylesheet reveals on `is-open`),
  so the menu button did nothing at mobile width.
- **The prototype server now sends `no-store`.** The data file is regenerated whenever the
  engine changes, and a browser holding an old copy shows last week's figures with this week's
  screens — silently, in front of whoever is being demoed to. That happened during this build.

A fourth, in the export itself: `clean()` was shipping **118 counts as JSON strings**. The page
rendered correctly only because JavaScript coerces them. Fixed, with a test that walks the
whole fixture looking for a number stored as text.

## Step 6 — the thin LLM layer

```
question ──parse──> EngineCall ──execute──> engine result ──narrate──> sentence
             ^                  (deterministic)                ^
             └── an LLM, or no LLM at all ────────────────────┘
```

`src/client_llm.py` has **no engine dependency**, so the call format can be reviewed and handed to
whoever builds the assistant without pulling in pandas. `src/client_ask.py` does the wiring.

**The call format is the frozen question catalogue.** Ten questions in the brief, ten intents.
A model that returns anything else is refused, not improvised around — a plausible answer to a
question nobody asked is worse than saying the question is not supported.

**Three guarantees that hold whichever provider is used.**

1. *The LLM never produces a number.* Narration is built from templates with engine values
   substituted. When a model phrases the sentence instead, every numeral in its output is
   checked against the engine result and the template is used if one was invented.
2. *A refusal survives translation.* Where the engine says it cannot estimate, the sentence
   says so. That is the thing a fluent model is most likely to smooth away.
3. *It can be left out.* `KeywordProvider` needs no model, no network and no key.

| Provider | For |
| --- | --- |
| `KeywordProvider` | the default. No model at all, so phase 1 ships without one |
| `HTTPProvider` | any OpenAI-compatible endpoint — vLLM, Ollama, llama.cpp. **The on-prem route** |
| `GeminiProvider` | the hosted option, fine for a demo |

A Saudi bank in a private cloud points `base_url` at its own server and nothing else changes.
That is why the protocol, not the vendor, is what the layer is built around.

### The ten questions, answered

```
$ python -m src.client_ask "which rules cost approvals without reducing risk?"
call    rules_not_earning_place  {'top': 5}
answer  5 rules cost approvals without buying safety. The largest is
        yknBasicCheckValidation#016, which alone declines 3,125 applicants whose
        estimated bad rate of 8.5% is no worse than the book's.
```

```
$ python -m src.client_ask "if I lower the SIMAH cutoff from 600 to 560, what happens?"
call    simulate  {'field': 'simahcreditscore', 'from': 600.0, 'to': 560.0}
answer  Moving simahcreditscore from 600 to 560 takes the approval rate from 21.9% to
        22.2%, approving 153 applicants who are currently declined. Their estimated bad
        rate is 8.36% against a booked 8.29%.
```

`python -m src.client_ask` with no arguments prints the call format.

## Tests

299 passing. The ones worth knowing about:

- Every planted answer from step 2 is asserted to be **recoverable by the engine**, not just
  present in the data. A ranking that looks plausible but is wrong is the failure mode the
  brief warns about throughout, and a known right answer is the only defence.
- Regression tests for each of the four simulator bugs above, all of which produced
  plausible-looking wrong numbers rather than errors.
- The LLM layer's tests are mostly about what it refuses: an invented intent, an invented
  parameter, an out-of-range value, an invented figure, a softened refusal.
- No test needs a network or an API key.

## What is still open

Carried from steps 1 and 2, and none of them guessed at:

1. **Evaluation order.** 33 overlapping bands mean order changes the outcome, and the
   `G`/`SG` age contradiction now demonstrably hits thousands of real rows.
2. **One pass or several?** `executionLevel` says `RAC` or `SIMATI`, which hints at two, but
   not their order.
3. **What happens when no rule matches** — approve or decline?
4. **`monthCnt` lost its operator in export.** Read as equality those rules almost never fire;
   read as minimums they decline 2.3% of applicants.
5. **No bureau rule applies to TWQR.** All 31 SIMAH rules are marked IJMB. Guru's hard-reject
   stage cannot be reproduced for the demo product from these files.

New from this work:

6. **The walk-away rate.** Guru described losing half the surviving applicants to slowness;
   this population loses 9.4%, set by hand for the demo (see the funnel above). The true figure
   is unknown, and the screens say the rate is a placeholder.
7. **22 policy codes are ambiguous**, and the screens show `policyCode` as the decline reason.
