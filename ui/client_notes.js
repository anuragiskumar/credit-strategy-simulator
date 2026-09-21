/* Spec notes for client.html: what each element on screen is and what it stands for.
 *
 * client.js tags an element with data-note="<key>"; when the spec-notes icon is on, every tagged
 * element gets a number and the matching entry below is printed as a footnote at the foot of the
 * page. Text only — no arithmetic, and nothing here is shown until the icon is pressed.
 *
 * Values that can change with the data or the config (rule count, ceiling, replay assumptions)
 * are read from the fixture rather than typed in, so a note cannot drift from the screen.
 * Thresholds that live only in config (exposure multiples, the "buys no safety" margin) are
 * described, not quoted, for the same reason.
 */
window.__NOTES__ = function (F) {
  'use strict';
  var m = F.meta || {};
  var dec = m.replay_decisions || {};
  var count = function (v) { return Number(v).toLocaleString('en-US'); };
  var ceiling = m.bad_rate_ceiling === undefined ? 'a set' : (Number(m.bad_rate_ceiling) * 100).toFixed(0) + '%';
  var unevaluable = m.rules_unevaluable || [];

  return {
    /* ------------------------------------------------------------ every screen */
    product: {
      t: 'Product: ' + m.product,
      d: 'The lending product being analysed: TWQR is Tawarruq personal finance, IJMB is Ijara. Each ' +
         'product\'s applicants are replayed against that product\'s own rules only. Choosing another ' +
         'product changes every figure on every screen, and clears any scenario in the Simulator.'
    },
    period: {
      t: 'Period: ' + (m.window ? m.window.label : 'all applications'),
      d: 'Which applications are replayed against the rules. It sets the funnel, the approval rate, the ' +
         'decline drivers and every scenario. It does not set the bad rate: recent loans have not had time ' +
         'to go bad, so the bad rate always comes from loans old enough to judge (see the period line).'
    },
    as_of: {
      t: 'Data as of',
      d: 'The extract date: the last day the data records. Nothing after it is observed, so a loan that went bad ' +
         'later still counts as good here. Read from config outcome.as_of' + (m.data_as_of ? ' (' + m.data_as_of + ')' : '') +
         '. Figures built is when the engine computed these figures: its last load or recompute when it is ' +
         'running, otherwise when this page\'s data file was exported.'
    },
    period_line: {
      t: 'What these figures cover',
      d: 'Counts and rates come from the applications in the period. The bad rate and the risk model come ' +
         'from booked loans that have run the whole performance window' +
         (m.window ? ' (' + m.window.performance_months + ' months)' : '') + ' by the extract date, wherever ' +
         'they sit in time. Loans booked more recently are not yet observable and are never counted as good.'
    },
    sim_context: {
      t: 'Scenario after a change of period or product',
      d: 'A new period re-runs your changes on the new applications, so the figures stay comparable with ' +
         'today in that period. A new product clears them, because its rules are different.'
    },
    rules: {
      t: count(m.rules_replayed) + ' rules replayed',
      d: 'Each rule is one row of the bank\'s decision tables: conditions on an applicant that end in a ' +
         'decline, a pass, or a cap on the amount offered. All of them were run against every one of the ' +
         count(m.applicants) + ' applicants.' +
         (unevaluable.length
           ? ' ' + count(unevaluable.length) + ' more (' + unevaluable.join(', ') + ') cannot be evaluated from ' +
             'the applicant data available. It is named here rather than silently treated as a rule that never fires.'
           : '')
    },
    strip: {
      t: 'Synthetic applicants, real rules',
      d: 'The ' + count(m.applicants) + ' applicants are generated, so no figure on any screen describes a real ' +
         'customer or a real book. The rules are real, and the method (replay every rule to see who is caught ' +
         'where) is the one that would run on real applications. The rule files do not say how rules combine, so ' +
         'three assumptions are made, and changing any of them moves the funnel: (1) an applicant is credited to ' +
         'the first rule, in table order, that catches them; (2) a condition on a missing value ' +
         (dec.condition_on_missing_value_matches ? 'matches' : 'does not match') + '; (3) an applicant no rule ' +
         'catches is ' + (dec.no_rule_matched === 'decline' ? 'declined' : 'approved') + '.'
    },
    rail_screens: {
      t: 'Screens',
      d: 'Portfolio: what the current rules book, and what that book is made of. Decline drivers: which rules ' +
         'decline the most applicants, and which could be relaxed without adding risk. Simulator: change one rule ' +
         'or one threshold and see who moves.'
    },
    rail_prov: {
      t: 'Provenance tags',
      d: 'Every figure carries a tag saying how it was arrived at, and colour is used for this and nothing else. ' +
         'OBSERVED: counted directly from the replay. PREDICTED: from the risk model, inside the population it ' +
         'was trained on. INFERRED: estimated for applicants the bank declined and never saw repay (reject ' +
         'inference). NOT MODELLED: the engine refuses to give a number, drawn hatched so an absence is never ' +
         'read as a value.'
    },

    /* --------------------------------------------------------------- portfolio */
    pf_head: {
      t: 'Portfolio',
      d: '"The current strategy" means the rules exactly as they stand, with nothing changed. This screen replays ' +
         'them over all applicants and shows what they book (the loans that survive every stage) and how that book ' +
         'is spread across segments. It is the baseline the Simulator moves away from.'
    },
    k_approval: {
      t: 'Approval rate',
      d: 'Booked loans as a share of all applicants. It is measured after every stage of the funnel, not only ' +
         'after credit policy, so applicants who are declined, capped below what they will accept, or who walk ' +
         'away all count against it.'
    },
    k_bad: {
      t: 'Booked bad rate',
      d: 'Share of booked loans that went bad. It is observed on the book only: declined applicants have no ' +
         'repayment history, so this is not a bad rate for the whole applicant population and should not be ' +
         'read as one.'
    },
    k_exposure: {
      t: 'Exposure',
      d: 'Total amount offered across all booked loans, in SAR, after every finance cap has been applied ' +
         '(bn = billion, m = million, k = thousand).'
    },
    k_gap: {
      t: 'Median offer gap',
      d: 'For a typical applicant, the amount requested minus the amount the rules allow to be offered. It is the ' +
         'median across all applicants, so a few very large cuts do not distort it. A large gap means finance ' +
         'caps are cutting the amounts lent.'
    },
    over_time: {
      t: 'Over time',
      d: 'How the product has moved, over the whole data file rather than the chosen period, so the period can be ' +
         'seen against what came before it. Every rate here is counted from the data; none is estimated.'
    },
    trend_lead: {
      t: 'By application month',
      d: 'Top: each month’s applications replayed against today’s rules, so a change in the approval rate is a change ' +
         'in who applied, not in the rules. Bottom: the bad rate of the loans those applications became, once they have ' +
         'run the whole performance window. A recent month has no bad rate yet: its loans that are still paying have not ' +
         'had the time to go bad, and counting them as good would make the recent book look safer than it is. A month ' +
         'gets a bad rate once most of its loans (the share is a setting) have run the window by the extract date, ' +
         'which is why the bad rate elsewhere on this page comes from older loans than the chosen period.'
    },
    trend_chart: {
      t: 'Trend chart',
      d: 'The shaded columns are the chosen period. The pale band in the lower chart covers the months too recent to judge. ' +
         'The dashed line is the bad-rate limit. Hover a point for its figures.'
    },
    tr_judged: {
      t: 'Loans judged',
      d: 'Booked loans from that month that have run the whole performance window by the extract date, and the share of ' +
         'the month’s booked loans they are. Only these count in the bad rate.'
    },
    vintage_lead: {
      t: 'Vintage',
      d: 'Every loan the bank actually booked, grouped by when it was booked, read from its booking date and the date it ' +
         'first reached the bad DPD. Each line is the share of that group gone bad after each month on book. Lines that ' +
         'rise faster, or sit higher, are worse business. A line is drawn only as far as every loan in it has run; ' +
         'where it reaches the performance window, its height is that group’s bad rate.'
    },
    vintage_chart: {
      t: 'Vintage chart',
      d: 'One line per booking quarter or month; the newest is the darkest. The dotted line marks the bad definition: ' +
         'where a line crosses it is that group’s bad rate. Hover a line for its figures.'
    },
    roll_rate: {
      t: 'Roll rates',
      d: 'Roll rates show how loans move between arrears buckets (30, 60, 90 days) month by month. They need each ' +
         'loan’s arrears history. The data contract today carries only the date a loan first reached the bad DPD, so ' +
         'they are not shown rather than guessed.'
    },
    funnel: {
      t: 'Where applicants drop out',
      d: 'Each applicant leaves at exactly one place: the first stage they fail. Two views of the same figures. ' +
         'Funnel: a glass vessel in which each green disc is who is still in, its width exactly proportional to that ' +
         'count, and the arrow leaving through the glass is who was lost there, its thickness growing with the loss. ' +
         'The screen opens on an empty funnel with focus on it, for a presenter: the right arrow key pours one ' +
         'stage at a time and the left arrow steps back (Home empties it, End pours the rest, Reset starts again). ' +
         'Every stage ends on the exported figures. Bars: each stage row is ' +
         'everyone who reached it, split into green (goes on) and grey (lost here). Dark grey is a loss the lender ' +
         'caused (a rule or a product limit); light grey, and a dashed arrow, is a customer who walked away. Losses ' +
         'are grey, not coloured, because colour on these screens only ever says how a figure is known. The losses ' +
         'sum to the application total minus the booked loans, which is the check that the picture is complete. ' +
         'Every stage is derived by replaying the rules, never assigned: the reason attached to each declined ' +
         'applicant is the rule that actually caught them.'
    },
    fview: {
      t: 'Funnel or Bars',
      d: 'The same model drawn two ways. Funnel shows the shape of attrition at a glance; Bars lines the stages up so ' +
         'their losses can be compared exactly. Switching keeps any open drill-down open.'
    },
    fdrill: {
      t: 'The rules behind a stage',
      d: 'Opened from a stage\'s chevron (Bars) or its loss arrow (Funnel). Lists the rules that caught the most ' +
         'applicants at that stage. Each applicant is counted once, under the first rule that caught them, so the ' +
         'counts add up to the stage total; if they ever do not, the difference is shown here rather than hidden. ' +
         'Sole cause is how many of them only that rule stops: remove just that rule and they pass every other ' +
         'rule (they may still fail a finance cap). A solid lock marks a rule the bank has declared a regulatory ' +
         'knock-out; a hollow one marks a rule inferred to be fixed because of the fields it tests.'
    },
    stage_applied: { t: 'Applied', d: 'Every application in the population, before any rule is run.' },
    stage_hard_reject: {
      t: 'Hard reject',
      d: 'Applicants stopped by basic validity and identity checks, such as age limits, before credit policy is considered.'
    },
    stage_credit_policy: {
      t: 'Credit policy',
      d: 'Applicants declined by the bank\'s credit policy rules: bureau scores, income, employer and similar tests.'
    },
    stage_eligibility: {
      t: 'Eligibility',
      d: 'Applicants who pass every rule but whose offer, once finance caps are applied, is below an acceptable ' +
         'share of what they asked for or below the product minimum. They are counted here rather than as declines.'
    },
    stage_walked_away: {
      t: 'Walked away',
      d: 'Applicants who were offered a loan and did not take it up. In this synthetic population the rate is a ' +
         'generated assumption, not something the rules decide, so treat it as a placeholder until real data is available.'
    },
    stage_booked: {
      t: 'Booked',
      d: 'Applicants who survived every stage and hold a loan. This count is the numerator of the approval rate and ' +
         'the base for exposure and the booked bad rate.'
    },
    slice: {
      t: 'The booked book, sliced',
      d: 'The same booked loans, grouped a different way with each button: employer segment, sector, channel, score ' +
         'band or nationality. Shares are of exposure (SAR lent), not of loan count, because concentration risk is ' +
         'about money. Each group reads by its business name, set in configuration; where the data carries a code ' +
         '(GOV, SAU) it is shown beside the name, and the CSV carries both.'
    },
    th_booked: { t: 'Booked', d: 'Number of booked loans in this group.' },
    th_exposure: {
      t: 'Exposure',
      d: 'Bar length shows the amount lent to the group, relative to the largest group in this view.'
    },
    th_share: { t: 'Share', d: 'The group\'s share of total exposure.' },
    th_bad: {
      t: 'Bad rate',
      d: 'Share of the group\'s booked loans that went bad. Observed only, so it is shown as a dash for a group ' +
         'with no booked loans.'
    },
    th_flag: {
      t: 'Flag',
      d: 'Concentration flag, measured against an even split across the groups shown. Over-exposed: the group holds ' +
         'a share far above its even share. Under-exposed: far below it. The multiples are configurable settings.'
    },
    ch_panel: {
      t: 'Declines by channel',
      d: 'Where applications come from (digital, branch, DSA or direct selling agent, telesales) and how much of ' +
         'the decline volume each channel accounts for. Only declines by rule (hard reject and credit policy) are ' +
         'counted; applicants lost at the eligibility cut or who walked away are not.'
    },
    th_ch_approval: {
      t: 'Approval',
      d: 'Booked loans as a share of the channel\'s applicants. Same definition as the headline approval rate, so ' +
         'channels can be compared with it directly.'
    },
    th_ch_declines: {
      t: 'Declines (bar)',
      d: 'Bar length shows the channel\'s rule declines relative to the channel with the most.'
    },
    th_ch_n: { t: 'n', d: 'The count of declined applicants behind the bar to its left.' },
    th_ch_share: {
      t: 'Share of declines',
      d: 'The channel\'s part of all rule declines. The channels sum to 100%.'
    },

    /* ---------------------------------------------------------- decline drivers */
    dr_head: {
      t: 'Decline drivers',
      d: 'The diagnosis: which rules cost approvals, and which are safe to loosen. Read-only. Every rule is grouped by ' +
         'the engine; the screen only draws the groups. Changes are made in the Simulator, which each rule links to.'
    },
    dr_q10: {
      t: 'Finding',
      d: 'Which rules cost approvals without reducing risk. A rule "buys no safety" when the applicants only it declines ' +
         'are estimated to be no riskier than the booked book, within the margin set in Settings (earn-its-place ' +
         'multiple). The approvals are counted; the risk is inferred.'
    },
    dr_t_review: {
      t: 'Could gain at little extra risk',
      d: 'Approvals the "Worth reviewing" rules would add, each loosened on its own and added up. Loosening several ' +
         'together can add more, because an applicant two of them both decline is freed only when both go. The ' +
         'Simulator shows the combined figure.'
    },
    dr_t_earning: {
      t: 'Earning their place',
      d: 'Rules whose applicants are estimated to be riskier than the book by more than the configured margin. ' +
         'Loosening them would add approvals and raise the bad rate.'
    },
    dr_t_noest: {
      t: 'Can\'t be judged',
      d: 'Rules the engine gives no risk estimate for: the applicants only they decline are too few, or sit outside ' +
         'anything the bank has booked (often no bureau score). A confident number there would invite loosening a rule for free.'
    },
    dr_chart: {
      t: 'Approvals against risk',
      d: 'One dot per rule the engine can judge. Right means more approvals if the rule is loosened on its own; up means ' +
         'a higher estimated bad rate for those applicants. The solid line is where a rule starts earning its place ' +
         '(today\'s booked bad rate times the configured margin); the dashed line is today\'s book. Solid dots are the ' +
         'rules worth reviewing. Rules with no estimate have no height, so they sit as ticks on the hatched strip.'
    },
    dr_rank: {
      t: 'Rules by verdict',
      d: 'Every decline rule, in the group the engine put it in: worth reviewing, earning its place, no estimate, only ' +
         'declines alongside other rules, not relaxable, rules that caught nobody in this period, and rules the data ' +
         'cannot evaluate. The top five of each are shown; the last four groups start closed. Together they are every ' +
         'decline rule the Simulator lists.'
    },
    th_rule: {
      t: 'Rule',
      d: 'The rule\'s business description first. Below it, the rule ID (decision table and row in the bank\'s rule ' +
         'files) and policy code, so any line can be traced back to its source.'
    },
    th_gain: {
      t: 'Approvals gained if loosened',
      d: 'How many more applicants would be booked if only this rule were switched off: the ones no other rule declines, ' +
         'less those who then fail eligibility or walk away. Replayed by the engine, not estimated. The grey figure is ' +
         'everyone the rule declines, including those another rule also declines.'
    },
    th_relaxed: {
      t: 'Bad rate if loosened',
      d: 'Estimated bad rate of the applicants only this rule declines, from the risk model (inferred: they have never ' +
         'been booked). NO ESTIMATE means the engine declined to guess; NOT RELAXABLE means the rule is off the table.'
    },
    dr_losses: {
      t: 'Where applicants are lost',
      d: 'Every reason an applicant does not end up booked, not only the rules: hard reject and credit policy are rules ' +
         '(listed above), eligibility is the offer falling below what the product or the applicant accepts, and walking ' +
         'away is the applicant\'s choice. Counted from the replay.'
    },
    dr_reasons: {
      t: 'Biggest reasons',
      d: 'The three largest reasons within each stage, credited to the first rule or condition that stopped the applicant.'
    },

        /* ---------------------------------------------------------------- simulator */
    sim_head: {
      t: 'Simulator',
      d: 'Start from today\'s rules and change them one step at a time. Every result is a replay of the same ' +
         'applicants under the changed rules, so "newly approved" is a set of actual applicants, not a projected ' +
         'percentage.'
    },
    sim_views: {
      t: 'Four views',
      d: 'Set a target answers "how do we reach X% approval?". Try a change answers "what if?" with a few ' +
         'ready-made stories, the two score cutoffs and the busiest rules. All rules is the analyst\'s ' +
         'workbench: every rule, every threshold. Try a change and All rules share one scenario. Saved lists ' +
         'the scenarios people have kept, and compares them side by side.'
    },
    csv: {
      t: 'CSV download',
      d: 'The table\'s rows as the engine produced them, not as the screen formats them: rates as fractions, ' +
         'counts as whole numbers, every column the engine sends. A column of estimates carries [INFERRED] in its ' +
         'header; the rest are counted. The file name carries the product and the applications replayed.'
    },
    sim_save: {
      t: 'Save scenario',
      d: 'Keeps the steps with a name, the product and the period. The engine re-runs them as it saves, so the ' +
         'figures kept are its own, and records who saved it and when. Names are unique per product.'
    },
    sim_print: {
      t: 'Print pack',
      d: 'One page for the committee: the product and period, how the bad rate was observed, each change in ' +
         'order with the rule it touches in words, the outcome against today with the provenance of every ' +
         'figure, and who prepared it. Save it as PDF from the print dialog.'
    },
    goal_print: {
      t: 'Print this option',
      d: 'The committee pack for one goal-seek option: what was asked for, the option\'s changes and outcome, ' +
         'and every other option the search returned, so the paper shows what was chosen against what.'
    },
    sim_saved: {
      t: 'Saved scenarios',
      d: 'Every scenario saved on this engine, newest first, with its figures as they were when saved and who ' +
         'saved it. Open re-runs it in its own product and period. Delete takes it off the list but keeps the ' +
         'record of who saved and deleted it.'
    },
    sim_compare: {
      t: 'Compare',
      d: 'Re-runs the ticked scenarios now, each in its own product and period, and lays them side by side. ' +
         'If the answer has moved since a scenario was saved (new data, a new rule pack) the comparison says so.'
    },
    sim_cmp_table: {
      t: 'Side by side',
      d: 'One column per scenario, all figures from the fresh re-run. Scenarios built on different products or ' +
         'periods are flagged: their figures are not measured on the same applications.'
    },
    sim_outcome: {
      t: 'The outcome bar',
      d: 'The whole book with every change in the scenario applied, against today. It stays at the top of the ' +
         'screen while you change things below it, so the answer is always in view.'
    },
    sim_legend: {
      t: 'What the colours mean',
      d: 'Colour says how a figure is known, never whether it is good. Green is counted from the replay. Orange ' +
         'is estimated, because the newly approved have never been booked, so nobody has seen them repay. Grey ' +
         'means no estimate is possible.'
    },
    sim_chart: {
      t: 'Approval against bad rate',
      d: 'Each dot is a whole book: today, your scenario or a goal-seek option. Right means more approvals; up ' +
         'means a higher bad rate. The dashed red line is the bad-rate limit, and anything in the shaded band ' +
         'above it is out of bounds. The line from Today shows the trade each change makes.'
    },
    sim_presets: {
      t: 'Ready-made stories',
      d: 'One click sets up a scenario worth talking about. The bottleneck is the rule that stops the most ' +
         'applicants on its own. "Loosen what Decline drivers flagged" takes the top rules that screen groups as ' +
         'worth reviewing; it reads that verdict and never works one out again. The downturn raises a score cutoff, so ' +
         'some applicants approved today are turned away.'
    },
    sim_cutoff: {
      t: 'Score cutoffs',
      d: 'Moving a cutoff moves every rule that tests that score at today\'s value, together. Left loosens, ' +
         'right tightens. The mark on the track is today\'s setting.'
    },
    sim_levers: {
      t: 'The busiest rules',
      d: 'The rules that, on their own, stop the most applicants. Switch one off to release them. The count is the ' +
         'most switching it off could release, before later stages take their share.'
    },
    sim_mode: {
      t: 'Engine or precomputed',
      d: 'With the engine running (python -m ui.serve) every change is replayed live, in a fraction of a second. ' +
         'Without it the screen falls back to scenarios worked out in advance, and says so here.'
    },
    sim_rules: {
      t: 'Every decline rule',
      d: 'All the rules that can decline an applicant for this product, grouped by the stage that evaluates them ' +
         'and busiest first. It opens on the rules that stop someone on their own, because switching off any other ' +
         'moves nobody. Search reaches every rule. The status says what your scenario does to each: On as today, ' +
         'Off, Changed (a threshold moved) or Locked.'
    },
    sim_pick: {
      t: 'Open a rule',
      d: 'Click a rule to open it. Its detail takes the place of the scenario panel (under the row on a narrow ' +
         'screen): what it declines in words, the switch, any threshold that can move, and the steps it already ' +
         'has in your scenario. The rows have no buttons, so nothing changes by accident.'
    },
    sim_alone: {
      t: 'Only this rule stops',
      d: 'Applicants this rule declines that no other rule does. It is the most that switching this one rule off ' +
         'could release, before later stages (the finance cap, walking away) take their share. The detail shows ' +
         'how many of them would actually be booked.'
    },
    sim_sentence: {
      t: 'The rule in words',
      d: 'Written by the engine from the same parsed conditions the replay evaluates, so it cannot say something ' +
         'the rule does not do. "Applies to" is the rule\'s scope: who it is tested on at all. A locked rule shows ' +
         'only this and the reason it is locked, with no control that would be refused.'
    },
    sim_edit: {
      t: 'Move a threshold',
      d: 'Move a number inside the rule instead of switching it off, for example the minimum income from 5,000 ' +
         'to 4,000: today\'s value on the left, the new one on the right, then Add to scenario. It works in both ' +
         'directions. Where the rule has a Pass twin (simati writes <3500 Fail and >=3500 Pass as a pair), both ' +
         'move together.'
    },
    sim_stack: {
      t: 'Your scenario',
      d: 'The changes so far, as a waterfall: today\'s approval rate, what each step added on top of the ones ' +
         'before it, and where they end up. × removes one step and replays the rest, so a change can be tried, ' +
         'judged and undone without starting again.'
    },
    sim_added: {
      t: 'What a step added',
      d: 'The change in approval rate, and in approved and declined applicants, that this step made on top of ' +
         'the steps before it. Steps overlap: a rule switched off after another may release fewer people than it ' +
         'would alone, because some were already released.'
    },
    t_approval: {
      t: 'Approval rate (after the change)',
      d: 'The book\'s approval rate with the scenario applied, and the change in percentage points (pp) from ' +
         'today. Releasing applicants from a rule rarely raises approvals by the full number released, because ' +
         'some of them then fail a later stage.'
    },
    t_in: {
      t: 'Newly approved',
      d: 'Applicants declined today who would be approved after the change (swap-ins). The bank has never seen ' +
         'them repay, which is why their risk is estimated rather than observed.'
    },
    t_out: {
      t: 'Newly declined',
      d: 'Applicants approved today who would be declined after the change (swap-outs). Switching a rule off or ' +
         'loosening a threshold can never decline anyone, so this is zero until a step tightens something. ' +
         'Swap-outs are booked loans, so their bad rate is observed, not estimated.'
    },
    t_bad: {
      t: 'Expected bad rate',
      d: 'The whole book after the change: the observed performance of the loans that stay booked, blended with ' +
         'the estimated risk of the newly approved. With nobody newly approved it is observed outright. Shown as ' +
         'NO ESTIMATE when the newly approved sit outside what the model can judge.'
    },
    verdict_tag: {
      t: 'VERDICT / UNKNOWN',
      d: 'The engine\'s one-sentence reading of the result. VERDICT means the change could be priced; UNKNOWN ' +
         'means it could not, and the sentence says why instead of giving a number.'
    },
    th_sw_channel: {
      t: 'Channel',
      d: 'The same swap-ins, broken down by the channel the application came from. A Newly declined column ' +
         'appears once a step tightens a rule; until then it would only ever show zeros.'
    },
    sweep: {
      t: 'Threshold sweep',
      d: 'Instead of switching a rule off, move a score cutoff. A sweep moves every rule that tests this score at ' +
         'once, in the direction that loosens it, and shows approvals and expected bad rate at each step.'
    },
    sweep_cell: {
      t: 'Reading a sweep cell',
      d: 'Top: the cutoff. Large figure: approval rate at that cutoff. Below it: the change from today in ' +
         'percentage points, then the expected bad rate, or "no estimate" where the extra approvals cannot be ' +
         'priced. The shaded cell is today\'s setting.'
    },
    goal: {
      t: 'Goal-seek',
      d: 'The simulator in reverse: set a target approval rate and the engine searches combinations of changes ' +
         '(switching rules off, moving cutoffs) that reach it. Every search is bounded by a bad-rate ceiling ' +
         '(default ' + ceiling + '), because "maximise approvals" on its own is solved by approving everyone.' +
         ' What comes back is a ranked shortlist for a person to take to a risk committee, not a decision and ' +
         'not a proof of optimality. Loosening a policy is a committee decision, not a calculation.'
    },
    goal_target: {
      t: 'Target approval rate',
      d: 'The approval rate to reach, as a share of all applications. Yours to set: it must be above today\'s.'
    },
    goal_ceiling: {
      t: 'Bad-rate ceiling',
      d: 'The highest expected bad rate the bank will accept for the new book. An option above it is flagged and ' +
         'never ranked first, however many approvals it buys.'
    },
    goal_frozen: {
      t: 'What the search may use',
      d: 'The rules the search is allowed to switch off: the busiest ones the bank may change. Click a rule to ' +
         'keep it on, and the search will not touch it. The cutoff moves it may also try are listed below.'
    },
    goal_reco: {
      t: 'The recommendation',
      d: 'The best package of changes the search found, in one sentence: the cheapest in extra bad rate among those ' +
         'that reach the target within the limit. If none does, the closest it could get.'
    },
    goal_apply: {
      t: 'Try this as a scenario',
      d: 'Loads the option\'s changes into Try a change, so you can see what each one adds and adjust from there.'
    },
    goal_more: {
      t: 'More options',
      d: 'The runners-up, best first. An option above the bad-rate limit is flagged and never ranked first, ' +
         'however many approvals it buys.'
    },
    goal_tag: {
      t: 'Reached / Out of reach',
      d: 'Whether any combination reaches the target within the ceiling. If it can, options are ranked by risk ' +
         'cost, not by the size of the change. If not, they are ranked by how close they get.'
    },
    opt_head: {
      t: 'Option',
      d: 'One candidate package of changes. It says whether it reaches the target, falls short, or would push the ' +
         'expected bad rate above the limit.'
    },
    opt_risk: {
      t: 'Bad rate and its change',
      d: 'How far the expected bad rate rises above today\'s, in percentage points. It is the price of the extra ' +
         'approvals and the key the options are ranked by. A dash means it could not be priced, and unpriced ' +
         'options are ranked last.'
    },
    opt_steps: {
      t: 'Changes in the option',
      d: 'The specific changes that make up the option, such as rules to switch off or cutoffs to move. Nothing is ' +
         'applied; this is a proposal.'
    }
  };
};
