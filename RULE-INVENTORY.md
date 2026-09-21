# Rule inventory — step 1

Generated from the four client Excel exports by `src/rule_inventory.py`.
Rebuild with `python -m src.rule_inventory`.

## What this is

Each Excel file is a **decision table**: one row per rule, one column per field, each cell a
condition. This step flattens all of them into one normalised table so the engine has a single
input format, and so duplicates and contradictions become visible.

Two tables are produced, both in `data/rule_inventory/`:

| File | Grain | Rows |
| --- | --- | --- |
| `rules.csv` | one row per rule | 402 |
| `conditions.csv` | one row per rule × field | 1,503 |
| `conflicts.csv` | one row per finding | 77 |
| `dead_columns.csv` | declared but never used | 10 |

## Rule count

The brief says 337. That is right for the four main sheets, but the files contain **402 rows
across 6 decision tables** — two were missed because they sit on second sheets.

| Decision table | Source file | Rows | Outcomes |
| --- | --- | --- | --- |
| `racAndPolicies` | racAndPolicies, Sheet1 | 260 | 37 Decline, 223 Exception |
| `simahRulesValidateAl` | simahRulesValidateAl, Sheet1 | 31 | 21 Fail, 10 Inactive |
| `simati_chk_IAF` | simati_chk_IAF, Sheet1 | 31 | 21 Fail, 10 Pass |
| `yknBasicCheckValidation` | yknBasicCheckValidation, Sheet1 | 15 | 15 Decline |
| **`yakeen-post-validation`** | simati_chk_IAF, **Sheet2** | **3** | 3 Decline |
| **`employer_keyword_check`** | racAndPolicies, **Sheet2** | **62** | 61 Y, 1 N |
| | | **402** | |

`employer_keyword_check` is a lookup, not a policy: 61 Arabic keyword tests on the employer name
(مؤسسة, مقاولات, صالون, بقالة …) that return Y/N. Ten `racAndPolicies` rules consume that Y/N.
It is a rule the bank can tune — it decides who counts as a small trader — so it is in the
inventory rather than hidden in a helper.

Policy rules proper: **340** (402 − 62 lookup rows).

## The normalised format

Every condition parses into `field · operator · value`. Nothing was left unparsed.

| Operator | Meaning | Source form | Count |
| --- | --- | --- | --- |
| `in` | value is in a set | `"ST","SMG","PVTL"` | 761 |
| `not_in` | value is not in a set | `not("SAU")` · `not("GOSI",null)` | 155 |
| `lt` `lte` `gt` `gte` `eq` | numeric comparison | `<600` · `>=3500` | 320 |
| `between` | inside a band | `[348.1..368]` | 71 |
| `outside` | outside a band, i.e. fails | `20 > age or age > 60` · `<12,>60` | 65 |
| `contains` | substring test | `contains(?, "مؤسسة")` | 61 |
| `income_multiple_exceeded` | affordability cap breached | `4*income<loanAmount` | 60 |
| `always` | matches everything | `"SAU", not("SAU")` | 10 |
| | | **1,503** | |

The income multiple also appears as an *action* rather than a condition — 62 Exception rows set
the cap to `4*income`, `10*income` and so on instead of a fixed amount. Those land in the rule
table's `cap_amount`, not here.

## Fixed vs tunable

The brief asks for a fixed/tunable tag. Three tags turned out to be needed, because many columns
say *who a rule applies to* rather than testing a credit criterion:

| Tag | Meaning | Conditions |
| --- | --- | --- |
| `scope` | which population the rule covers — segment, product, programme | 555 |
| `fixed` | a fact the bank cannot negotiate — nationality, PEP, bureau events, staff | 472 |
| `tunable` | a number the bank chose and could change | 476 |

**The tags are a proposal, not the client's own classification.** They need a human to confirm —
compliance decides what may be decided on, per the brief.

### The tunable levers, ranked

| Field | Rules | Distinct thresholds |
| --- | --- | --- |
| `loanAmount` | 126 | 18 |
| `simahCreditScore` | 102 | 3 — only 600, 650, 700 |
| `age` | 72 | 18 |
| `income` | 67 | 7 — 0, 2000, 3500, 5000, 10000, 15000, 40000 |
| `crifScore` | 25 | 7 |
| `tenure` | 20 | 2 |
| `lengthOfService` | 15 | 3 |
| `downpaymentPer` | 6 | 3 |

**102 rules turn on just three SIMAH cutoffs.** That is the demo's strongest single sentence:
move one number and you move a hundred rules at once. This is the direct answer to Guru's
*"what is that one thing I change?"*

## Findings

### 1. Zero bureau rules apply to the demo product

The demo product is TWQR. `simahRulesValidateAl` — the entire bureau file, all 31 rules — is
marked `IJMB`. **No SIMAH bureau rule applies to TWQR at all.**

| | Rules applying to TWQR |
| --- | --- |
| `racAndPolicies` | 188 |
| `simati_chk_IAF` | 21 |
| `yknBasicCheckValidation` | 15 |
| `yakeen-post-validation` | 3 |
| `simahRulesValidateAl` | **0** |
| **Total** | **227** |

Guru's funnel puts 70 of every 100 applicants into *hard rejects — blacklist, negative bureau
score*. On these files, that stage cannot be reproduced for TWQR. Either the TWQR bureau rules
live in a file we have not been given, or TWQR genuinely screens on `simahCreditScore` inside
`racAndPolicies` instead. **Worth asking the client before step 2**, because it decides whether the
synthetic population needs a bureau-reject stage at all.

### 2. The 223 Exception rows are two different things

The brief describes them all as amount caps. They split:

| Kind | Rows | What it does |
| --- | --- | --- |
| `amount_cap` | 126 | caps finance — 100k, 200k, 500k, 1.5M SAR, or a multiple of income |
| `eligibility_limit` | 97 | age band, tenure, length of service, minimum down payment |

These behave differently in the simulator: **a cap moves the offer, a limit moves the applicant
out of the funnel.** A cap is Guru's *eligibility cut* stage (offered below requested); a limit
is his *credit policy decline* stage. Conflating them would put people in the wrong funnel row.

The cap is not always in one column. When `requestAmount` is 0, the real cap is the amount the
`loanAmount` trigger fires above — `loanAmount > 1500000` with `requestAmount = 0` means the cap
is 1.5M. The loader resolves this.

### 3. Conflicts and data-quality findings — 77 in total

| Kind | Count | What it means |
| --- | --- | --- |
| `overlapping_band` | 33 | two rules, same outcome, nothing separating them, overlapping populations, different thresholds |
| `duplicate_policy_code` | 22 | one `policyCode` used by rules with different conditions |
| `tautology` | 10 | `nationality = "SAU", not("SAU")` — matches everyone |
| `description_mismatch` | 7 | the customer-facing text cites a number the rule does not use |
| `duplicate_identical` | 4 | same product, same conditions, same outcome — a redundant row |
| `restated_per_product` | 1 | one policy written once per product |

**Worked examples.**

- `yknBasicCheckValidation` rows 2 and 16: segments `G`,`SG` are capped at **age 20–60** by one
  row and **30–70** by another, same outcome, nothing else separating them. A 25-year-old
  government employee is declined by one row and accepted by the other. Whichever the engine
  evaluates first wins.
- `racAndPolicies` row 15 declines at `crifScore <= 690`, but the reason shown to the customer
  reads *"CRIF SCORE < 626"*. Row 246 declines at `<= 571` and says *"<= 605"*.
- 23 rules describe a SIMAH band as *"0 to 590"* while the condition is `< 600`. Scores 591–599
  are declined by a rule whose own text says they should not be.
- `yknBasicCheckValidation` rows 13–15 tell the customer *"Age is not between 20 or 75"* when
  the rule actually starts at 25.
- `PCAPL184` is attached to three different rules, `PCAPL185` to four. The brief plans to show
  `policyCode` as the decline reason on screen — **that will be ambiguous for 22 codes** until
  The client disambiguates them.

### 4. Ten dead columns

Declared in a decision table, never given a value in any row:

`ntb` · `V_EMPLOYMENTTYPE` · `V_COMP_APPL_ID` · `V_SCR_ASSET_MAKE` · `V_SECTOR_TYPE` ·
`gender` · `isBsfEmployee` · `"A"` · `empSegment` · `employeeType`

`V_SECTOR_TYPE` matters: Guru asked to slice the portfolio **by sector**, and the rules capture
no sector at all. Sector has to come from the application data, not from these files.

### 5. Channel is almost absent

`sourceType` is populated in **1 of 260** `racAndPolicies` rules (`not("digital")`). Guru's
question 4 — *which channel produces the most declines* — and the Alpha client's 980 digital
declines cannot be answered from the rules. Channel is an attribute of the **application**, so
the synthetic generator in step 2 must carry it, and decline-driver analysis must join on it.

## What this unblocks, and what it does not

**Unblocked (step 2).** The real field list for the synthetic generator, with real value sets:
`customerSegment` (ST, SMG, PVTL, PVTSML, …), `nationality` (SAU / non-SAU),
`typeOfEmployment` (CV / ML), `simahCreditScore`, `crifScore`, `income`, `age`,
`lengthOfService`, `employerName`, `militaryRank`, `downpaymentPer`, `pensioner`, PEP flags.
Thresholds tell the generator where to put mass so the bands are actually populated.

**Not answered, and needed before step 3.**

1. Do the 337 rules have an **evaluation order**? Decision tables usually do, and the overlapping
   bands mean order changes the outcome. No column in the export carries a priority.
2. Are `Decline`, `Fail` and `Exception` evaluated at the same stage, or in sequence? The
   `executionLevel` column says `RAC` or `SIMATI`, which suggests two passes, but not their order.
3. What does the engine do when **no rule matches**? Approve by default, or decline?

These are three questions for the client, not guesses to make. Getting them wrong would make the
decline-driver ranking — the LT demo's headline output — wrong in a way that still looks
plausible, which is the failure mode the brief already flagged for random rejection reasons.

## Caveats

- **Before sharing any of this externally**, confirm sharing is permitted under the NDA with the client,
  as the brief requires. The four `.xlsx` files are untracked and should stay that way; the tests
  skip themselves when the files are absent.
- No applicant-level personal data was found in any sheet. The only personal-ish strings are
  employer names and Arabic business-type keywords.
- The fixed/tunable tags are this tool's proposal and need compliance sign-off.
