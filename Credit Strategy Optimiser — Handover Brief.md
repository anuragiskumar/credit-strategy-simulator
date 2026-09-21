# Credit Strategy Optimiser — Handover Brief

2026-09-20 · @Someone

## Purpose of this document

This is a handover brief for the credit strategy optimiser. It carries everything decided and learned so far, so work can continue in a fresh chat without repeating the background.

**How to use it:** paste this document into a new chat and name the step to pick up. The immediate next step is in *Plan to the demo*, near the end.

## The product

A credit strategy simulation and optimisation engine that does what a bank's credit risk data scientist does today: analyse applications and portfolio performance, find which policy parameters drive declines, simulate changes against historical data, and recommend strategies to hit a target approval rate.

Source: stakeholder call with Guru L and Sayantani Saha, 20 Sept 2026 (44 min).

**What Guru asked for, in his words**

- "What is that one thing I change? It'll change my approval rate."
- Set a goal, e.g. 30% approval, and have the system return options A, B, C that reach it.
- Replace the data scientist: "the idea here is I want to get rid of all data scientists."
- Analyse the portfolio by slicing and dicing on sector, occupation, income, family size and score bands, then map each slice to performance.
- He referenced Experian's "strategy optimisation" as the model, and simulating against the last 6–12 months of applications.

**The funnel he walked through (per 100 applications)**

| Stage | Left | Why people drop |
| --- | --- | --- |
| Applied | 100 | — |
| Hard rejects | 70 | Blacklist, negative bureau score; nothing can be done |
| Credit policy declines | 40 | Work experience, score, income rules |
| Eligibility cut | 20 | Offered amount below requested, or below product minimum |
| Customer walked away | 10 | Bank took too long; customer went elsewhere |

**Scale:** about 600 applications a day at the first client, up to 1,000+ for the largest client. Sayantani estimated roughly 1M records to process; Guru agreed but neither figure was verified.

**Agreed on the call:** the LLM is a thin interaction layer only — plain English in, narrated results out. All numbers come from a deterministic engine. Guru was to think further about the LLM's role; Sayantani was to research the data scientist workflow, then produce mock-ups.

## What needs to be built

1. **Data layer with an extensible schema.** Applications with the outcome and reason at each stage, sourcing channel and agent, product parameters (min/max amount, eligibility ratio), and the booked portfolio with performance (DPD buckets). Guru was explicit that new data sources — alternative data, payments data, SME invoicing — must plug in later without a redesign.
2. **Policy/rule engine.** Rules from the bank's own policy, bureau scorecards, the bank's scorecard and third-party APIs, each flagged fixed (blacklist, bureau) or tunable, able to replay historical applications.
3. **Funnel / leakage analysis.** The stage-by-stage table above, with a reason attached at each stage. Where the bank does not capture a reason, the system derives it — Guru said so explicitly.
4. **Decline-driver analysis.** Which rule declines the most applicants on its own, broken down by channel, source and agent. At the Alpha client, 980 declines all came from the digital channel.
5. **Portfolio analytics.** Slices by segment and score band mapped to performance, plus concentration and gap flags (his example: IT at 80%, finance at 5%, no government exposure).
6. **What-if simulation.** Change one or more tunable parameters, replay the last 6–12 months, show the new approval rate and the risk impact.
7. **Goal-seek optimiser.** Enter a target approval rate, get ranked options that reach it.
8. **LLM interaction layer (thin, optional).** Natural language in, narration out. No decisions.

**Out of scope, or separate systems**

- Per-application underwriter assist (show similar past cases, suggest approve/decline). Both agreed this is a different system reusing the same data.
- Early warning system using macroeconomic indicators — a future use case.
- Alternative data, NTC scorecards and SME data ingestion — future, but the schema must allow for them.
- LLM ingestion of competitor benchmark policies — an idea only.
- Champion/challenger testing on live traffic — cannot be done offline.

**Two gaps nobody raised on the call**

- **The optimiser needs a risk constraint.** "Maximise approval rate" alone is solved by approving everyone. The real goal is maximum approval subject to a bad rate ceiling.
- **Reject inference.** Declined applicants have no repayment history, so replaying rules shows the approval impact but not the risk impact of newly approved applicants. This is where ML earns its place; the simulation and optimisation themselves are rule replay plus search.

## What a credit risk data scientist does

This is the task list the engine automates. Most of it is data analysis; only a small part is machine learning.

| # | Task | What it means | Needs ML? |
| --- | --- | --- | --- |
| 1 | Define "bad" | Fix the outcome definition, e.g. 90+ days past due within 12 months | No |
| 2 | Vintage / roll-rate analysis | Group loans by booking month, track how each group goes delinquent | No |
| 3 | Rule hit analysis | For each rule: how many it declines, how many it declines alone, how risky they look | No |
| 4 | Scorecard build | Bin variables, compute Weight of Evidence and Information Value, fit logistic regression, scale to points, validate with Gini/KS | Yes |
| 5 | Cutoff analysis | Approval rate and expected bad rate at each possible cutoff | No |
| 6 | Swap-set analysis | Who newly gets approved vs newly declined when strategy changes, and whether the swap-ins are riskier | No |
| 7 | Reject inference | Estimate how declined applicants would have performed | Yes |
| 8 | Champion/challenger | Run the new strategy on a slice of live traffic before rollout | No |
| 9 | Monitoring | Check the applicant population and score stay stable over time (PSI) | No |

**Three things around this still need a human, at least at first**

- **What's allowed.** Code can find that a field predicts well; it cannot know the bank may not decide on it. That is compliance's call.
- **Leakage.** A field that predicts too well is usually a consequence of the outcome, not a cause. Code can flag it; judging it needs business knowledge.
- **Acting on a finding.** Loosening a policy is a risk-committee decision, not a calculation.

The realistic design: the engine produces ranked lists with flags, and a human approves. That is also easier to sell to a bank than a black box, and matches Guru's description of leadership deciding policy changes.

## What we did in the Kaggle notebook

We used the public LendingClub dataset as stand-in bank data and replicated the data scientist's workflow by hand, to understand it before automating it. The dataset is `wordsforthewise/lending-club` on Kaggle: an accepted-loans file (2.26M loans, \~150 columns) and a rejected-applications file. A corrected, documented copy of the notebook exists as `lendingclub-analysis-documented.ipynb`.

**Do not use LendingClub data in the client demo.** The uploader's own note says LendingClub now shows a terms-of-service popup on download and may have it taken down. It is for learning only.

| Cell | What it does | What it found |
| --- | --- | --- |
| 1 | List the attached files | Both files, compressed and uncompressed |
| 2 | Load 12 of \~150 columns | 2,260,701 loans; 878,317 still being repaid |
| 3 | Label good vs bad | 21.2% bad rate — inflated |
| 4 | Keep only finished years (performance window) + vintage table | **13.95% honest bad rate**; bad rate rose from 10.6% (2011) to 14.9% (2015) while volume grew \~20× |
| 5 | Bad rate by grade, FICO band, employment length | Grade 5.5%→38.8%; FICO 16.4%→3.3%; **employment length flat at 12.6–14.5%** |
| 6 | Loans with blank employment length | 36,169 loans at **20.5% bad** — the riskiest group |
| 7 | What-if machine v1: accepted + rejected, move the score cutoff | Above 660 a real trade-off curve; below 660 the bad rate is stuck at 14.5% because those people were never funded |
| 8 | Compare accepted vs rejected scores | No approved applicant below 660; some rejected scores reach 990, so part of that column is not FICO |
| 9 | Coverage check | 4.79M rejected applications in 2014–15, **54% with no score at all**; real acceptance ≈ 12% |
| 10 | PD model (logistic regression) + what-if v2 | Gini 0.258 (weak); predicted 14.0% vs actual 14.9% for 2015 (drift); rejected applicants scored as safe as accepted ones, which is implausible |

**The three findings that matter most**

1. **A rule can cost approvals without buying safety.** Employment length barely predicts risk here, yet Guru's example policy was "more than 5 years' experience." This is exactly the "what one thing do I change?" answer the product must produce.
2. **Blank fields carry signal.** Standard grouping drops them silently, and the 20.5% bad rate almost went unnoticed. The engine must treat missing as its own segment everywhere.
3. **The simulator must say "we don't know."** Below the historical cutoff, a confident number is dangerous — it tells a CxO to loosen a rule for free.

**Still not done on this data:** Information Value ranking across all fields, swap-set analysis, PSI monitoring, goal-seek. These are formulas; the decision was to write them as engine modules rather than repeat them by hand. Rule hit analysis, funnel stages and sourcing channel are impossible on LendingClub at all — no rules, no reasons, no channel.

## Glossary

| Term | Plain English |
| --- | --- |
| Bad loan | A loan written off, defaulted, or seriously late (31–120 days) |
| Bad rate | The share of loans in a group that went bad |
| Performance window | Counting only loans old enough to have finished. Bad loans end early, good loans run the full term, so counting unfinished loans overstates the bad rate |
| Vintage | All loans issued in the same period, tracked as a group |
| DPD | Days past due — how late a borrower is |
| FICO / SIMAH / CRIF | Credit bureau scores. FICO is US (300–850); SIMAH and CRIF are the Saudi ones in the client's rules |
| DTI | Debt-to-income: the share of income already going to debt payments |
| PD model | A model that estimates each applicant's probability of default |
| Gini / AUC | How well a model ranks risky borrowers above safe ones. Gini runs 0 (coin toss) to 1 (perfect); 0.3+ is usable |
| Information Value (IV) | One number per field saying how well it separates good from bad. Under 0.02 useless, over 0.3 strong, over 0.5 suspicious — check for leakage |
| Leakage | A field that predicts too well because it is a consequence of the outcome, not a cause |
| Reject inference | Estimating how declined applicants would have performed, since they have no repayment history |
| Swap set | Who newly gets approved (swap-ins) and newly declined (swap-outs) when a rule changes |
| PSI | Population Stability Index — checks whether the applicant mix has shifted over time |
| Drift | Patterns changing over time, so a model trained on older data under- or over-predicts |
| Deterministic | Same input, same output every time. Rule replay and ML inference are deterministic; LLM output is not |

**ML vs analysis, since this caused confusion on the call.** A machine learning model is not a formula written by humans. Humans choose the model type and its inputs; the model works out the weights itself from the data. It is deterministic at prediction time, which is what banks care about. Most of this product is not ML at all — counting, grouping, replaying rules and searching over settings. ML appears in the PD model and reject inference. Goal-seek is optimisation, not ML.

## The client's rule files

Four Excel files from the client, exported from a rules engine as decision tables. **337 rules in total**, covering two products: TWQR (Tawarruq personal finance) and IJMB (Ijara). They contain rules only — no applicant data, no outcomes.

| File | Rows | Contents |
| --- | --- | --- |
| `racAndPolicies` | 260 rules, 37 fields | Risk Acceptance Criteria: 37 outright Decline rules plus 223 Exception rules that cap maximum finance by segment |
| `simahRulesValidateAl` | 31 rules | Bureau (SIMAH) rules: delinquency history, defaults, bounced cheques, court judgements. 21 Fail, **10 marked Inactive** |
| `simati_chk_IAF` | 31 rules | Employment and income verification: age, salary, length of service. 21 Fail, 10 Pass |
| `yknBasicCheckValidation` | 15 rules | Age bands by employee segment, including military sub-types |

Guru expected 30–40 policies. The real count is roughly ten times that, because each policy is written as many rows — one per segment and score combination. The engine must handle that expansion.

**Why these files are valuable**

1. **The format is already policy-as-config.** Each row is a rule, each column a field, each cell a condition: `<600`, `>=3500`, `not("SAU")`, `[15000..9999999]`. Our config format can mirror this, so the client could hand over rules without a rewrite.
2. **Ten SIMAH rules are marked Inactive.** The client already switches rules on and off by hand. That is the behaviour this product automates, and it is the strongest demo hook: *you already do this manually — here is what each switch costs you.*
3. **The 223 Exception rows are amount caps** (e.g. 100,000 and 200,000 SAR by segment). That is the eligibility stage of Guru's funnel, in real numbers.
4. **Decline reasons are already coded** — `policyCode` values such as `PCAPL184`, with Arabic and English descriptions. Screens can show the bank's own reason text.
5. **The real field list** for our schema and synthetic data: customer segment, nationality, SIMAH score, CRIF score, income, age, length of service, employment type, military rank, employer name, employer keyword, PEP flags, pensioner status, source type, downpayment percentage.

**Before using them:** confirm sharing is permitted under any NDA with the client, and check no sheet holds applicant-level personal data.

## Data strategy

**Decision: generate synthetic client-shaped applicants, then replay the client's real 337 rules over them.**

One option considered and rejected: use the LendingClub accepted + rejected files as the applicant population and assign each rejected row a random rejection reason from the client's policies. It fails for two reasons.

- **Random reasons break the product.** Every rule would decline a similar share, so the decline-driver ranking becomes noise that still looks plausible. Worse, the simulator stops working: moving "minimum salary 3,500 → 3,000" changes nothing, because the reason was never connected to the applicant's salary. There is also no right answer to test the engine against.
- **The fields do not match.** The client's rules need SIMAH score, CRIF score, nationality, customer segment, employment type, length of service, employer name and SAR income. LendingClub records none of them.

**The rule: derive, don't assign.** Give each synthetic applicant real field values, then let the client's rules decide who is declined and why. The reason then follows from the data, the ranking is real, and moving a threshold genuinely moves people between outcomes.

**What LendingClub is still good for**

- **Realistic shapes** — income distributions, income-to-requested-amount relationships, how score relates to default rate. Purely invented data looks too clean and a banker spots it instantly.
- **Real outcomes** — it records who actually defaulted. No synthetic dataset can. The PD model built in Cell 10 stays useful as the risk-estimation piece.

**Plant known answers in the synthetic data** (e.g. "the digital channel causes 80% of declines") and check the engine finds them. That is how you test a tool meant to replace human judgement.

**Say this plainly in the demo:** the applicants are synthetic, so the numbers are illustrative. What is real is the rules and the method. Claiming the numbers are real would not be acceptable.

## Plan to the demo

**Next step: build the rule inventory.** Convert all 337 rules from the four Excel files into one normalised table — rule id, product, segment, field, operator, value, outcome, source file, and a fixed-vs-tunable tag. It is both a deliverable and the engine's input format, and it surfaces conflicts and duplicates, which is a finding in itself. Everything below depends on it.

| Step | What | For |
| --- | --- | --- |
| 1 | Rule inventory from the four Excel files | LT demo |
| 2 | Synthetic client-shaped applicants (\~50k) with channel, funnel stages, outcomes, planted answers | LT demo |
| 3 | Rule replay + funnel + decline-driver ranking | LT demo |
| 4 | Simulator: change a threshold, show approval and risk impact | Client demo |
| 5 | Three CxO screens: portfolio, decline drivers, simulator | Client demo |
| 6 | Thin LLM layer, swappable between external API and on-prem | After |

**For the LT demo, steps 1 and 3 are enough.** The story is: *here are your 337 real rules, and here is which ones cost you the most approvals.* Steps 4 and 5 target the client demo on 10 Oct 2026.

**Question catalogue (frozen).** The engine is done when it answers these ten. Anything else is a later phase.

1. What is my approval rate, and on what base — all applications, or only those that reached a decision?
2. Where do applicants drop out, stage by stage, and how many at each stage?
3. Which rule declines the most applicants on its own, with no other rule catching them?
4. Which channel, source or agent produces the most declines?
5. How does my portfolio split by segment and score band, and how does each slice perform?
6. Where am I over- or under-exposed compared with the market I could lend to?
7. If I change this threshold, what happens to approvals and to expected bad rate?
8. Who newly gets approved and newly declined by that change, and are the swap-ins riskier?
9. What combination of changes reaches a target approval rate, ranked by risk cost?
10. Which of my rules cost approvals without reducing risk, and which ones earn their place?

**LLM: phase 2 of the demo, not phase 1.** Its only job is translation in both directions — turn a naturally asked question ("how do I get to 30% approval?") into a call the engine understands, and turn the engine's output back into a sentence. It computes nothing and decides nothing. That means it can be swapped freely and can be left out of phase 1 without changing the product.

Options available: a Gemini API key already in hand, plus Modal and Kaggle accounts that could host an open-source model behind an API call. For Saudi banks running on-prem or in a private cloud, an external API is likely a non-starter, so the open-source route is the one that generalises. Either works for a demo; build the engine's call format first so the LLM has something well-defined to translate into.

**Answered (20 Sept 2026)**

| Question | Answer |
| --- | --- |
| What does "Inactive" mean on the 10 SIMAH rules? | The rule was live at some point and has since been switched off |
| Will we get application-level data with outcomes? | Not from the first client. Another client will provide data, expected Tuesday |
| Which product for the demo? | TWQR |
| Can we demo the client's real rules against synthetic applicants? | Yes, as long as no client is named in the demo |
| Does the bank capture a decline reason at every stage? | Unknown until the client data arrives |

**Still open**

- [ ] How the simulator should present the risk side of a loosening, given performance only appears after \~6 months. Build a first version, check with Guru.
- [ ] Show Guru the findings — flat employment length, blank fields as a signal, the reject inference limit — and confirm this is the analysis he means.

**Because real client data arrives Tuesday:** build the rule replay and funnel against synthetic data now, but keep the loader separate from the engine, so the real file can be mapped into the same schema without touching the analysis code.

## How to continue in the new chat

**Context for whoever picks this up.** I have no Python, no ML and no statistics background, and I have never met a data scientist. Explain concepts with everyday analogies before any code or maths, and check I follow before moving on. The *Glossary* section is the level that worked.

**Working style that has worked so far**

- One step at a time, with output pasted back and reviewed before the next step.
- No speculation presented as fact. Say what the data shows, and say when something is an assumption.
- Command-first: give the thing to run or do, then explain it.

**Files to have on hand**

- `lendingclub-analysis-documented.ipynb` — the corrected notebook with documentation above each cell.
- The four client rule files: `racAndPolicies`, `simahRulesValidateAl`, `simati_chk_IAF`, `yknBasicCheckValidation`.
- The stakeholder call transcript from 20 Sept 2026.

