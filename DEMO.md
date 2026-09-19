# Demo script

A 15–20 minute walkthrough. The narrative is deliberately not "look how many more people we can
approve" — it is **"here is an answer, and here is exactly how much of it we actually know."** That
is the differentiator, and audiences who have seen approval-optimisation pitches before recognise
it immediately.

## Pre-flight (do this before the room)

```bash
source .venv/bin/activate && python -m src.generate_data && pytest -q
```

Expect eight `[PASS]` calibration lines and 123 passing tests. Then:

```bash
streamlit run app/streamlit_app.py
```

Open **Overview**, wait for the dataset to cache, then click through all eight pages once so
Streamlit has warmed every cache. Click the run buttons on **Optimiser** and **Portfolio Quality** —
those two pages do nothing until clicked, and a cold optimiser run in front of an audience is four
seconds of silence you do not need.

Have a terminal open on a second window. Being able to drop out of the UI and show
`python -m src.optimise` producing the identical numbers is the most convincing thirty seconds in
the whole demo: it proves the UI is a view, not the product.

## The walkthrough

**1. Overview — establish the baseline and the honesty.** One million applications, 398,646
approved (39.86%), observed bad rate 2.86%. Then the number nobody else shows: strategy
reproduction is **99.00%**, and **100.00%** once manual overrides are excluded. Say why that
matters — if we cannot reproduce your current strategy exactly, every simulation on top of it is
decoration. The 1% gap is fully accounted for, override by override, in both directions.

**2. Decline waterfall — where the 601,354 declines actually go.** R5_SCORE 27.4%, R6_FOIR 12.1%,
R3_THIN_FILE 9.1%, R4_BUREAU_HIST 5.1%, R1_AGE 5.0%, R2_FRAUD 1.9%. The steps sum to the
application total on screen. Point at **single-rule declines** — applicants who failed exactly one
rule. That is the near-miss population and it is where the rest of the demo happens.

**3. Risk model — the part most products skip.** AUC, calibration by decile, coefficients. Then
spend real time on **training support**: the model is only entitled to speak about the region it
has seen. Show the count of applicants sitting in a dense decile bin but outside the booked
min–max — those get **no PD at all**, not a confident extrapolation.

Then the **near-cutoff anchor**. Manual overrides give genuine observed performance below the
cutoff. Measured across the whole score band, the implied penalty is **1.063**; measured within
matched score × FOIR × employment cells it is **0.895**. They disagree in *sign*. Show both. The
line to say out loud: *"the naive comparison here gives the opposite answer, and most tools would
have shown you the naive one."*

**4. What-if — the obvious move, and why it is the wrong one.** Drop the cutoff from 700 to 680.
Approvals rise; the blended bad rate rises with them. Show the observed / model-basis / inferred /
blended split, and the `NOT_MODELLED` panel. Then relax the bureau-history rule and let the
extrapolation warning fire: *N of these approvals cannot be scored at all, and the rate shown
covers only the remainder.*

**5. Optimiser — the actual product.** Run it. Approval rate **39.86% → 51.20%**, **+113,341**
approvals, blended bad rate **3.499%** against a 3.50% cap.

Do not stop on that slide. Immediately show the three things beside it:

- **Binding constraint: `bad_rate`.** The strategy spent its entire risk budget; 17 candidate
  segments were rejected. This is what "we optimised" actually means.
- **Candidate funnel:** 601,354 declines → 387,944 failing only score/FOIR → 319,214 inside
  training support → 172,531 in viable segments. Ten segments out of a pool the audience can see.
- **THIN share: 94.4%.** Most of the recommended approvals sit in cells with fewer than 100
  observed booked customers behind them. Say this before they find it.

Then the **naive comparison**: a uniform cutoff drop to 678 buys 474,462 approvals at the same bad
rate. The targeted strategy buys **37,525 more approvals at the same risk**. That number is the
commercial case, and it is only credible because everything above it was disclosed.

**6. Portfolio quality — the page with no inference in it at all.** Every figure here is `OBSERVED`.
Rank currently approved segments by **contribution to total bads**, not by rate — a three-customer
segment at 66.7% is noise, and 49 of 59 cells fall below the size floor and together hold 0.5% of
the book. Then the decline list, which is a *different* list: only segments whose rate and whose
confidence lower bound both exceed the portfolio average, ranked by excess bads.

The combined trade comes out **negative** on this data, and that is the most valuable thing on the
page. The segments worth declining are large and sit above 700; their replacements are smaller and
sit below the cutoff. Show the exchange rate and let them decide. A swap-out page whose answer is
always yes is a sales tool.

**7. Validation — close by marking your own homework.** Synthetic data only, and labelled as such.
Predicted versus true, side by side, including the true bad rate of the `NOT_MODELLED` approvals
that the headline excluded. State plainly that this page has no counterpart on real data — which is
exactly why the provenance labelling on every other page exists.

## Questions you will get

**"Can it recommend breaching a regulatory limit?"** On the shipped build, the affordability rule is
commercially relaxable, so today the honest answer is that mandatory rules (age, fraud) cannot be
bypassed by any path and are tested for it, and that the regulatory rule class is specified in
REQUIREMENTS.md Section 16.3 and lands in the deployable build. Do not overclaim this one; it is
the question a credit risk head asks to find out whether you are serious.

**"How do you know the declined customers would have performed like that?"** You do not, and the
product says so on every screen. There is a conservatism penalty of 1.25, a sensitivity strip at
1.0/1.25/1.5/2.0, a breakeven penalty, and 94.4% of the recommendation is flagged THIN. The honest
framing: *this is a shortlist for a champion/challenger test, not a strategy to publish on Monday.*

**"Your breakeven penalty is 1.2508 and you are running at 1.25 — is this recommendation one
rounding error from breaching?"** Good question, and the answer is structural rather than alarming:
the greedy adds segments until the constraint binds, so whenever `binding_constraint` is `bad_rate`
the breakeven necessarily lands just above the operating penalty. It is informative when the run is
slot-bound. The sensitivity strip is the figure to read instead, and it is on the same screen.

**"Will this work on our data?"** The loader validates a fixed schema and a real dataset with those
columns drops straight in; field mapping from their column names is configuration, not code
(REQUIREMENTS.md Section 22.3). The honest caveat is that the data-readiness report comes first and
usually finds something.

## Do not say

- Do not present any inferred figure as observed. The product will contradict you on screen.
- Do not quote the combined trade as a win. It is negative, deliberately.
- Do not promise the Part B platform features as present. Sections 16–31 are specified and
  scheduled; the CxO deck covers them as architecture, and Section 17 has the dates.
- Do not show the INR figures to a Saudi audience without flagging that the dataset is synthetic
  demo data pending localisation (REQUIREMENTS.md Section 31.4).
