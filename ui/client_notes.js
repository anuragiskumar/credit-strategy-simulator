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
      d: 'The lending product being analysed. TWQR is Tawarruq personal finance. Only the decision ' +
         'rules that apply to this product are replayed; rules belonging to other products are left out.'
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
    funnel: {
      t: 'Where applicants drop out',
      d: 'Each applicant leaves at exactly one place: the first stage they fail. Two views of the same figures. ' +
         'Funnel: each green band is who is still in, its width exactly proportional to that count, and the arrow ' +
         'leaving each narrowing is who was lost there, its thickness growing with the loss. Bars: each stage row is ' +
         'everyone who reached it, split into green (goes on) and grey (lost here). Dark grey is a loss the lender ' +
         'caused (a rule or a product limit); light grey, and a dashed arrow, is a customer who walked away. Losses ' +
         'are grey, not coloured, because colour on these screens only ever says how a figure is known. The losses ' +
         'sum to the application total minus the booked loans, which is the check that the picture is complete.'
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
         'counts add up to the stage total; if they ever do not, the difference is shown here rather than hidden.'
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
         'about money.'
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
    conc: {
      t: 'CONC',
      d: 'A plain-language reading of the Flag column: which groups carry more or less of the book\'s exposure than ' +
         'an even split would give them.'
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
      d: 'Ranks rules by how many applicants they decline, and separates two numbers that are easily confused: ' +
         'everyone a rule catches, and the applicants it catches that no other rule does. Only the second is what ' +
         'you would gain by changing that rule.'
    },
    dr_q10: {
      t: 'Q10',
      d: 'The tenth of the ten business questions this engine is built to answer: which rules cost approvals ' +
         'without reducing risk. A rule "buys no safety" when the applicants only it declines are estimated to be ' +
         'no riskier than the book already carries, within a configurable margin. That estimate is inferred, not observed.'
    },
    dr_rank: {
      t: 'Ranked by applicants declined alone',
      d: 'Sorted by the Alone column, largest first. The counts are observed from the replay. The risk figure is ' +
         'an estimate (inferred), for the reasons given under RISK below the table.'
    },
    th_rule: {
      t: 'Rule',
      d: 'The rule\'s identifier (decision table and row number in the bank\'s rule files) and the start of its ' +
         'description, so any line can be traced back to its source.'
    },
    th_declines: {
      t: 'Declines',
      d: 'Every applicant the rule catches, including those another rule would also decline.'
    },
    th_allalone: {
      t: 'All / alone',
      d: 'Two bars on one scale. The pale bar is everyone the rule declines; the dark bar is the applicants it ' +
         'declines alone. A large gap between them means the rule mostly overlaps with others.'
    },
    th_alone: {
      t: 'Alone',
      d: 'Applicants declined by this rule and no other. It answers "what is the one thing I change?": switching ' +
         'the rule off releases exactly these applicants.'
    },
    th_relaxed: {
      t: 'Bad rate if relaxed',
      d: 'Estimated bad rate of the applicants who would be released if the rule were switched off, from the risk ' +
         'model (inferred: they have never been booked). NO ESTIMATE means the engine declined to guess; NOT ' +
         'RELAXABLE means the rule is off the table.'
    },
    why_alone: {
      t: 'WHY ALONE',
      d: 'Explains the Alone column: switching off a rule whose declines are all shared with another rule frees ' +
         'nobody, because the other rule still catches them.'
    },
    risk_tag: {
      t: 'RISK',
      d: 'Declined applicants have no repayment history, so the bad rate of relaxing a rule is inferred by a model ' +
         'trained only on booked loans. Where a group sits outside anything the bank has booked, or is too small ' +
         'to judge, the engine returns NO ESTIMATE instead of a confident number.'
    },
    dr_guard: {
      t: 'Rules the engine will not judge',
      d: 'Rules that rest on a regulatory or identity fact (such as politically exposed persons, diplomatic ' +
         'service or staff) are never offered as relaxations, whatever they cost in approvals. The engine can ' +
         'measure what a rule costs; it cannot know whether the bank is allowed to drop it. This is a fixed list, ' +
         'not a judgement the model makes.'
    },
    th_rests: {
      t: 'Rests on',
      d: 'The applicant field the rule tests, which is what makes it non-negotiable.'
    },

    /* ---------------------------------------------------------------- simulator */
    sim_head: {
      t: 'Simulator',
      d: 'Change one thing and see who moves. Every result is a replay of the same applicants under the changed ' +
         'rule, so "newly approved" is a set of actual applicants, not a projected percentage.'
    },
    sw_panel: {
      t: 'Switch one rule off',
      d: 'Each button is a rule. Choosing one replays the whole book as if that rule did not exist. Compare the ' +
         'result with the current position on the Portfolio screen.'
    },
    t_approval: {
      t: 'Approval rate (after the change)',
      d: 'The book\'s approval rate with the selected rule off, and the change in percentage points (pp) from ' +
         'today. Releasing applicants from one rule rarely raises approvals by the full number released, because ' +
         'some of them then fail a later stage.'
    },
    t_in: {
      t: 'Newly approved',
      d: 'Applicants declined today who would be approved after the change (swap-ins). The bank has never seen ' +
         'them repay, which is why their risk is estimated rather than observed.'
    },
    t_out: {
      t: 'Newly declined',
      d: 'Applicants approved today who would be declined after the change (swap-outs). For a pure relaxation ' +
         'this is zero; a non-zero figure would mean the change tightened something.'
    },
    t_bad: {
      t: 'Expected bad rate',
      d: 'The whole book after the change: the observed performance of the loans that stay booked, blended with ' +
         'the estimated risk of the newly approved. Shown as NO ESTIMATE when the newly approved sit outside what ' +
         'the model can judge.'
    },
    verdict_tag: {
      t: 'SWAP-IN / UNKNOWN',
      d: 'The engine\'s one-sentence reading of the result. SWAP-IN means the newly approved could be priced; ' +
         'UNKNOWN means they could not, and the sentence says why instead of giving a number.'
    },
    th_sw_channel: {
      t: 'Channel',
      d: 'The same swap-ins and swap-outs, broken down by the channel the application came from.'
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
      d: 'The simulator in reverse: pick a target approval rate and the engine searches combinations of changes ' +
         '(switching rules off, moving cutoffs) that reach it. Every search is bounded by a bad-rate ceiling of ' +
         ceiling + ', because "maximise approvals" on its own is solved by approving everyone.'
    },
    goal_tag: {
      t: 'REACHED / OUT OF REACH',
      d: 'Whether any combination reaches the target within the ceiling. If it can, options are ranked by risk ' +
         'cost, not by the size of the change. If not, they are ranked by how close they get.'
    },
    opt_head: {
      t: 'Option',
      d: 'One candidate package of changes, best first. REACHES TARGET or FALLS SHORT says whether it gets there. ' +
         'BREACHES BAD-RATE CEILING means it would push the expected bad rate over the ceiling, so it is never ' +
         'ranked first however high its approval rate.'
    },
    opt_risk: {
      t: 'Risk cost',
      d: 'How far the expected bad rate rises above today\'s, in percentage points. It is the price of the extra ' +
         'approvals and the key the options are ranked by. A dash means it could not be priced, and unpriced ' +
         'options are ranked last.'
    },
    opt_steps: {
      t: 'Changes in the option',
      d: 'The specific changes that make up the option, such as rules to switch off or cutoffs to move. Nothing is ' +
         'applied; this is a proposal.'
    },
    limit: {
      t: 'LIMIT',
      d: 'The output is a ranked shortlist for a person to take to a risk committee, not a proof of optimality. ' +
         'Loosening a policy is a committee decision, not a calculation.'
    }
  };
};
