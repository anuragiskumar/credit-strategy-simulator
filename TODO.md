# TODO

Gaps found in the gap analysis of `ui/client.html` on 2026-09-21. This list is still growing.

Each item has a priority (P0 = blocks the on-prem release on real data, P1 = expected by
stakeholders, P2 = nice to have), the reason it's missing, and what "done" means.

---

## A. Analysis window (dates)

The stakeholder asked: *"How does a user choose the dates of the applications they want to analyse?"*
Today they can't. `app_date` is in the schema ([src/client_schema.py](src/client_schema.py)) and the
generator fills it, but nothing after generation reads it. Every screen analyses the whole file.
The brief asks for a replay of "the last 6–12 months of applications". We met that by generating
exactly 12 months of data, not by making the window selectable.

There are two windows, and both are missing:

| Window | Question it answers |
|---|---|
| Application window | Which applicants are replayed against the rules? |
| Performance window | Which booked loans are old enough for their bad rate to mean anything? |

### A1. Real-data outcome contract — P0
- [x] Add `booking_date`, an observed outcome (a flag, or DPD plus observation date) and a declared
      "bad" definition (for example 90+ DPD within 12 months) to the canonical schema and loader.
- [x] Separate the synthetic `latent_bad` (ground truth, never seen by the engine) from the
      observed outcome a real bank supplies. Today `observed_bad` is read from `latent_bad`
      ([src/client_analysis.py](src/client_analysis.py) `outcome()`).
- [x] Generator: derive booking and outcome dates so that recent loans are genuinely immature.

**Done when:** a real bank file with booked outcomes loads and runs without a `latent_bad` column.

### A2. Analysis window as an engine parameter — P0
- [x] One `AnalysisWindow {app_from, app_to, performance_months}` object, carried in config and on
      every request.
- [x] Build a baseline (replay, outcome, PD model) per window. Cache recent windows, because a
      baseline takes about 3 seconds to build.
- [x] Application mask: sets who is replayed, which drives the funnel, approval rate, drivers and
      swap sets.
- [x] Maturity mask: only booked loans older than `performance_months` feed the bad rate and PD
      training. Show immature loans as "not yet observable". They must not count as good.
- [x] Make the window part of each scenario's identity, and have every simulate and goal-seek
      result report the window it ran on.

**Done when:** choosing "last 3 months" can't make the bad rate look better just because loans
haven't had time to go bad.

### A3. API — P0
- [x] `/api/health` returns the available date range and the default window.
- [x] `/api/simulate` and `/api/goal-seek` accept `window`.
- [x] The engine rejects a window with too few applicants or too few mature loans, and gives the
      reason in words (`ApiError`), the same way it rejects a locked rule.

### A4. UI — P1
- [x] A global period control in the top bar, next to the product chip. Presets: last 6 months,
      last 12 months, custom. The performance window goes under an advanced setting.
- [x] Print the chosen period on every screen and in the demo strip.
- [x] When the period changes, reset the Simulator scenario, or re-run it with a warning.
- [x] Fixture mode: precompute two or three windows so the offline demo can still show the control.

### A5. Tests — P0
- [x] Window boundaries (inclusive/exclusive, empty window).
- [x] Immature loans are excluded from the bad rate and from PD training.
- [x] The same window gives the same figures through the CLI, the API and the fixture export.

---

## B. Other gaps of the same kind

### B1. Product selector — P1
The brief covers TWQR and IJMB, and `compile_rules(product=…)` already supports both. But the
product chip is static and `product: TWQR` is fixed in `config_client.yaml`.
- [x] Make product a request parameter, the same way the window is (the baseline is per product and window).
- [x] Make the product chip a selector.

### B2. Trend over time / vintage — P1
The brief lists vintage and roll-rate analysis as step 2. None of it is built.
- [x] Approval rate and bad rate by application month. A month shows a bad rate only once 95% of
      its loans have run the performance window; the recent months say when they will be judged.
- [x] Vintage curves by booking month or quarter, from the bank's own booking and bad dates.
- Roll rates stay out: they need each loan's monthly arrears, and the data contract carries only
  the date a loan first reached the bad DPD. The panel says so. Adding them means extending the
  contract with a monthly DPD history.

### B3. Export — P1
Leadership approves policy changes, so they need something to take into the committee meeting.
- [x] CSV download for each table.
- [x] PDF or print pack for a scenario or goal-seek option: the changes, the outcome, the
      provenance and the analysis window.

### B4. Save, name and compare scenarios — P1
Today a Simulator scenario is lost on reload. Only the page name is kept in the URL hash.
- [x] Save a scenario with a name (steps, product, window).
- [x] Compare two or more saved scenarios side by side.
- [x] Record who saved what, and when (fits with the ABAC / admin work). Until the server
      authenticates people, "who" is the name the page sends; the ABAC identity goes in that field.

### B5. Data "as of" date — P2
`meta.generated` exists but isn't shown, and real data has no extract date.
- [ ] Show the data extract date and the fixture build time in the UI.

### B6. Global filters — P2
Slicing only works in the Portfolio table.
- [ ] Scope the whole analysis (funnel, drivers, simulator) to a segment or channel, for example
      GOV only. This uses the same request-context mechanism as A2 and B1.

---

## Added after further analysis

## C. Screen redesign

From the page-by-page review on 2026-09-21. The common problem: each screen shows everything it
knows, with the explanation written out in full, instead of answering the one question its user
came with.

### C0. Decline Drivers and Simulator overlap — P1
The two screens show the same numbers. Decline Drivers "Alone" (for example 4,444 for
`racAndPolicies#012`) is the same figure as the Simulator's "only this rule stops", and "Bad rate
if relaxed" is the result of switching one rule off. The finding "11 rules cost approvals without
buying safety" appears three times: the Drivers callout, the Simulator presets
([ui/client.js](ui/client.js) `presets()`), and the All rules counts.

What differs is scope. Drivers looks at one rule at a time, so it can't show overlap: two rules
that catch the same applicants each show zero freed by switching them off alone. Only the
Simulator can show that.

Decision: keep both screens, each with a distinct job, and show the finding once. The demo story
is Portfolio (where am I?) → Decline Drivers (why?) → Simulator (what if?).
- [x] Decline Drivers is the diagnosis: read-only, no controls. Broaden it beyond rules to every
      reason applicants are lost (hard reject, eligibility caps, walk-aways), and end each row
      with "Try in Simulator →".
- [x] Simulator All rules becomes a picker for building a scenario (see C2), not a second ranking.
- [x] Simulator *Try a change* presets stop recomputing the Drivers finding. They open with "the
      rules Decline Drivers flagged" and link back to that screen.
- [ ] Revisit after the demo: merge the two into one "Rules" screen with a Diagnose / Change
      switch, but only if the audience turns out to be mostly analysts.

### C1. Decline Drivers redesign — P1 (quick wins before the demo)
User: a CRO or CxO asking "which rules cost me approvals, and which are safe to loosen?"
Problems: a 50-word callout that names rules by ID; the engine ID leads each row; three columns
(Declines, bar, Alone) for one idea; the "Bad rate if relaxed" column mixes four kinds of answer
(a number, "buys no safety", NO ESTIMATE, NOT RELAXABLE); 25 flat rows; two explanatory
paragraphs; and a second table repeating four rows.
- [x] Three headline tiles: could gain approvals at no extra risk / earning their place / can't be judged.
- [x] One chart: approvals each rule blocks on its own against the bad rate if relaxed, with a
      line at today's booked bad rate. Dots below the line are free approvals. Dots are INFERRED;
      rules with no estimate sit as a hatched strip on the axis.
- [x] Group the table by verdict (Worth reviewing → Earning their place → No estimate → Not
      relaxable, collapsed), top 5 in each with "show all".
- [x] Business name first, rule ID secondary in mono. One number column, "Approvals gained if
      loosened", with total declines as a grey secondary figure.
- [x] The "Why alone" and "Risk" paragraphs move to ⓘ tooltips and spec notes.
- [x] Rules that catch nobody (currently on Settings) move here as their own group.
- [x] **Before the demo:** business names first, a one-line callout, and the table grouped by verdict.

### C2. Simulator → All rules — P1 (before the demo)
Every one of the 113 rows has a checkbox, an "Edit threshold" button and a line of raw conditions,
so the list reads as a debug table. The checkbox doesn't say what it means.
- [x] List on the left, detail on the right. Rows: business name, rule ID, "only this rule stops"
      count, and a status tag (On / Off / Changed / Locked). No buttons on the rows.
- [x] Clicking a row opens its detail in place of the scenario panel (or as a drawer): the
      conditions as a readable sentence, an On/Off switch, the threshold editor (current value →
      new value), and "Add to scenario".
- [x] Group rows by stage (Hard reject / Credit policy / Eligibility), collapsible. Default filter:
      "Stops someone on its own".
- [x] Rules that can't be edited show only the lock and the reason. No button that gets refused.

### C3. Settings overhaul — P1
Today it's a read-only list of facts about the build (workbook file names, table roles, config
values). Nothing on it can be changed, and some of it belongs to IT or to other screens.
- [x] **Analysis tab:** period and product, which the analyst can change (the home for A4 and
      B1), plus rule pack version and last refresh. Everyone else can read it.
      _Built: product and period are each viewer's own view (the same store as the period
      control on every screen), so anyone may change them; it changes nothing anyone else sees.
      Making them an analyst-owned default for everyone would need a server-side setting._
- [x] **Risk appetite tab:** bad-rate ceiling as the headline, the multiples under "Advanced".
      Maker/checker editing: propose → approve → takes effect on next recompute, with who
      approved each value and when. It also takes in "Never relaxed" and "What goal-seek may move".
      _Built on `src/client_policy.py`: the engine refuses an approval by the proposer. Recompute
      is real with the engine running. "Never relaxed" and the goal-seek moves are shown here and
      still set in config._
- [x] **Replay assumptions tab:** the three switches in plain language, with the impact beside
      each (for example "affects 16% of applicants"). Only the approver can edit them.
      _The impact is counted by replaying with each switch flipped: missing values 2.7% of TWQR,
      inactive rules 0%. `no_rule_matched` is never read by the engine, so it is shown as fixed._
- [x] **Data health tab:** fields with missing values, and rules the data can't evaluate.
- [x] Move the workbook and table inventory to Administration → Data. Business users see one
      line: "226 rules from 4 workbooks, updated 20 Sep".
      _Moved to Administration → Rule workbooks, with the audit log._

### C4. Administration overhaul — P1
User: the bank's IT or application admin. They want to know "is it healthy, is data flowing, who
has access, and does anything need me?"
- [ ] **Overview first:** status cards (Licence · Data · Mapping · Version). Only the ones needing
      attention expand. The licence goes large only when it's actually expiring.
- [ ] **Licence moves to the bottom.** Fold "signature verified" into the status line, keep
      Licence ID (support reference), and move Algorithm and Fingerprint under "Technical details"
      or drop them. They are for Azentio support, not the client.
- [x] **Field mapping is inconsistent:** it says "11 of 24 mapped. Nothing can run" while the app
      runs. Show the real state, or make it a clearly labelled mapping wizard.
- [x] **"Outcomes and performance" claims something the engine doesn't do** (90 DPD / 12 months,
      performance source). Label it as planned configuration or remove it until A1 lands.
- [ ] **Add the missing admin work:** Users & access (who has which role, SSO status) and an
      audit log you can view and filter, not only export.
- [ ] Data source: replace the Oracle / PostgreSQL / MySQL tabs with a "connect a source" flow.
- [ ] Sections: Overview · Data (source, mapping, outcomes, rule workbooks) · Users & access ·
      Audit log · System (platform, security, regional, versions, support bundle) · Licence.

### C5. Patterns across all screens — P2
- [ ] One layout for every page: the answer (tiles or a sentence) → the evidence (one chart or
      table) → detail on demand. No explanatory paragraphs in the default view.
- [ ] Business names everywhere; engine IDs secondary.
- [ ] Provenance pills only where a figure appears, not on section headers.
- [ ] Each fact lives in one place. Applicant count and period currently appear on Settings,
      Administration and the demo strip.

<!-- Add new items here. -->
