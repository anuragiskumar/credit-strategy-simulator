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
- [x] Show the data extract date and the fixture build time in the UI.
      _Done: under the period line on every analysis screen and in the committee export: "Data as of
      31 Aug 2026 (config outcome.as_of) · figures built …". With the engine running, built is its
      last load or recompute, not when the view was asked for._

### B6. Global filters — P2 · NOT DOING (decided 2026-09-21)
Slicing only works in the Portfolio table.
> Not doing: more trouble than it is worth. Rules apply to every applicant, so a simulator scoped to
> one segment would flatter a change that hits the whole book; small segments would also hit the
> too-few-mature-loans refusal often. The Portfolio table already slices by segment, sector,
> channel, score band and nationality, and Drivers and the simulator already split by channel.
> If it is ever wanted: scope only the funnel and drivers, and keep the simulator on the whole book.
- [ ] ~~Scope the whole analysis (funnel, drivers, simulator) to a segment or channel, for example
      GOV only. This uses the same request-context mechanism as A2 and B1.~~

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
- [x] **Overview first:** status cards (Licence · Data · Mapping · Version). Only the ones needing
      attention expand. The licence goes large only when it's actually expiring.
- [x] **Licence moves to the bottom.** Fold "signature verified" into the status line, keep
      Licence ID (support reference), and move Algorithm and Fingerprint under "Technical details"
      or drop them. They are for Azentio support, not the client.
- [x] **Field mapping is inconsistent:** it says "11 of 24 mapped. Nothing can run" while the app
      runs. Show the real state, or make it a clearly labelled mapping wizard.
- [x] **"Outcomes and performance" claims something the engine doesn't do** (90 DPD / 12 months,
      performance source). Label it as planned configuration or remove it until A1 lands.
- [x] **Add the missing admin work:** Users & access (who has which role, SSO status) and an
      audit log you can view and filter, not only export.
- [x] Data source: replace the Oracle / PostgreSQL / MySQL tabs with a "connect a source" flow.
- [x] Sections: Overview · Data (source, mapping, outcomes, rule workbooks) · Users & access ·
      Audit log · System (platform, security, regional, versions, support bundle) · Licence.
      _Done: six tabs. Overview answers "does anything need me?" and opens only the cards that do
      (licence goes large only past Active; data opens on a failed recompute). The audit log merges
      the engine's own settings records (proposals, decisions, recompute) with example events,
      filters in place and downloads what is shown. Users & access and the source flow are preview._

### C5. Patterns across all screens — P2
- [x] One layout for every page: the answer (tiles or a sentence) → the evidence (one chart or
      table) → detail on demand. No explanatory paragraphs in the default view.
      _Portfolio lost four: the funnel's method note and the Over time method moved to spec notes,
      roll rates went behind "Why no roll rates", and the concentration caveat went (the Flag
      column says it). Settings' product and period chooser sits behind "Change product or period"._
- [x] Business names everywhere; engine IDs secondary.
      _Segment, sector, channel and nationality read by name from `value_labels` in config (GOV
      and SAU stay beside the name; CSVs carry both), score bands read "651–700", and data columns
      by name from `client_schema.LABELS`. The rule Settings can't evaluate reads by description._
- [x] Provenance pills only where a figure appears, not on section headers.
      _11 moved: onto the column or tile the figure is in, or a key under a chart._
- [x] Each fact lives in one place. Applicant count and period currently appear on Settings,
      Administration and the demo strip.
      _The strip now says only what it is for. The dataset's size and dates are on Administration →
      Data alone. "Figures built" on the analysis screens is now the engine's time when it is
      running, the same as Settings and Administration show (they disagreed by the export gap)._

## D. Every screen size — phone to boardroom TV

Found on 2026-09-21 from a photo of `client.html` on a large monitor: the content stops at 1180px
and sits on the left, so half the screen is empty, and the text is too small to read across a room.
The demo is pushed a week so this is fixed properly, not patched.

**Why it happens.** `.canvaswrap { max-width: 1180px }` in `ui/tokens.css` has no
`margin-inline: auto`, and `tokens.css` is shared, so `client.html`, `settings.html`, `admin.html`
and `index.html` all show the same gap. Under that, the UI is built from 1,231 fixed `px` values
and 33 viewport `@media` rules, and the charts are SVGs with a fixed `viewBox` (720 / 620 / 560
wide) stretched to their panel. Nothing scales from one source, so every new screen size needs its
own patch.

**Not doing:** CSS `zoom` on `.app` at large widths. It breaks the JS that measures (the funnel's
`clientWidth`, the Simulator's `--simstick`, the product/period menu and tooltip positions, pointer
coordinates on the funnel) and does nothing for phones or tablets.

**Order:** D1 → D4 carry the risk and go first; D5 is the WOW and needs sketches approved; then
D6, and D7 closes it. Estimate 3–4 focused days.

### D1. One size scale — P0 (before the demo)
- [ ] A fluid root size: `html { font-size: clamp(14px, 0.35vw + 9px, 20px) }` (tune the numbers).
- [ ] A type scale and a spacing scale as tokens in `tokens.css` (`--fs-1…`, `--sp-1…`) in `rem`.
      Other CSS uses only these names.
- [ ] Convert every `px` in `tokens.css`, `client.css`, `settings.css` and `shell.css`: type,
      spacing, the rail (`--rail`), the ledger (`--ledger`), radii where they matter. Hairline
      borders stay `1px`.
- [ ] Done when a 1440px screenshot of every page is unchanged before and after, and browser zoom
      and the OS text size still scale the whole UI.

### D2. Layout that grows and centres — P0 (before the demo)
- [ ] `--content-max` in `rem` (for example `90rem`) on `.canvaswrap`, with
      `margin-inline: auto` and fluid padding (`clamp(…)`), so width and text grow together and
      the top bar, demo strip and content share their edges.
- [ ] Keep the reading limits (`max-width: 66–78ch`) on prose.
- [ ] Settings and Administration forms (`.su-grid`) capped at about 60rem so text boxes don't
      stretch; card grids and tables keep the full width.

### D3. Components answer to their container, not the viewport — P0 (before the demo)
- [ ] Replace the viewport `@media` rules with container queries on `.canvaswrap` and `.panel`:
      the Simulator's two columns (`.simgrid`, today `max-width: 1180px`), tiles (`.tiles.c3/c4`),
      the drivers and rule tables, the funnel bars (`.fbars`).
- [ ] `narrowRules()` in `client.js` reads the same container width instead of a `matchMedia`.
- [ ] Done when the Simulator's narrow side column, a tablet and a TV each get the right layout
      from the same rules.

### D4. Charts drawn at their real size — P0 (before the demo)
- [ ] One chart helper: measure the box (`ResizeObserver`), draw at that pixel width, redraw on
      resize. Tick and label sizes come from the type scale, not from `viewBox` stretching (at TV
      width the stretched axis text is about 28px).
- [ ] Height by rule: an aspect ratio with a minimum and a maximum.
- [ ] Move the trend and vintage charts (`client.js:144`, `:228`), the drivers chart (`:934`) and
      the Simulator chart (`:1339`) onto it.
- [ ] Funnel: label columns (172 / 232), band heights (30 / 54) and the leak run in
      `FunnelModel.geometry()` scale with the root size, so the glass keeps its shape instead of
      going flat when it widens. Presenter mode (opens empty and focused, arrow keys pour it) must
      not change.

### D5. Wide screens show more, not stretch — P1 (before the demo, needs sketches approved)
Container-query layouts for a canvas wider than about 1400px. Sketch each one for approval first.
- [ ] **Portfolio:** the headline tiles and the funnel side by side; trend and vintage charts
      side by side below.
- [ ] **Decline drivers:** the chart beside its rule table.
- [ ] **Simulator:** controls, outcome chart and the step breakdown all in view with no scrolling.

### D6. Presenter size control — P1 (before the demo)
No browser knows how far the audience sits: a 1920px TV across a boardroom needs larger text than
a 1920px desk monitor.
- [ ] A 100 / 125 / 150% control in presenter mode that steps the root size. One setting, in the
      same place as everything else. Remembered per browser.

### D7. Verification — P0 (before the demo)
- [ ] Automated screenshots at 375, 768, 1280, 1440, 1920, 2560 and 3840px, light and dark, of
      Portfolio, Decline drivers, Simulator, every Settings section and all six Administration
      tabs. Keep them as the baseline so later changes can't quietly break a size.
- [ ] Manual pass: a full presenter-mode funnel pour, the Simulator's sticky columns while
      scrolling, the product/period menu and tooltips at each width, the print pack unchanged.

<!-- Add new items here. -->
