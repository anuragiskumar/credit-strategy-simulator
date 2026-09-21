window.__SETTINGS__ = {
 "meta": {
  "generated": "2026-09-21 10:03 UTC",
  "product": "TWQR",
  "synthetic": true,
  "note": "Rule set, dataset facts, field requirements and policy values are read from the engine. Everything under `simulated` is not."
 },
 "rulepack": {
  "files": [
   {
    "file": "business-rules-racAndPolicies-1788085705618.xlsx",
    "sha12": "2b79f0ec1ad4",
    "modified": "20 Sep 2026",
    "tables": [
     {
      "table": "racAndPolicies",
      "role": "decision table",
      "stage": "credit_policy",
      "rules": 260,
      "in_scope": 188,
      "inactive": 0
     },
     {
      "table": "employer_keyword_check",
      "role": "lookup",
      "stage": null,
      "rules": 62,
      "in_scope": 0,
      "inactive": 0
     }
    ]
   },
   {
    "file": "business-rules-simahRulesValidateAl-1788085655663.xlsx",
    "sha12": "07f76adf837e",
    "modified": "20 Sep 2026",
    "tables": [
     {
      "table": "simahRulesValidateAl",
      "role": "not replayed",
      "stage": null,
      "rules": 31,
      "in_scope": 0,
      "inactive": 10
     }
    ]
   },
   {
    "file": "business-rules-simati_chk_IAF-1788085737982.xlsx",
    "sha12": "1e969f31c6c9",
    "modified": "20 Sep 2026",
    "tables": [
     {
      "table": "simati_chk_IAF",
      "role": "decision table",
      "stage": "credit_policy",
      "rules": 31,
      "in_scope": 21,
      "inactive": 0
     },
     {
      "table": "yakeen-post-validation",
      "role": "decision table",
      "stage": "hard_reject",
      "rules": 3,
      "in_scope": 3,
      "inactive": 0
     }
    ]
   },
   {
    "file": "business-rules-yknBasicCheckValidation-1788085798680.xlsx",
    "sha12": "fa32d8ebf656",
    "modified": "20 Sep 2026",
    "tables": [
     {
      "table": "yknBasicCheckValidation",
      "role": "decision table",
      "stage": "hard_reject",
      "rules": 15,
      "in_scope": 15,
      "inactive": 0
     }
    ]
   }
  ],
  "totals": {
   "files": 4,
   "tables": 6,
   "rules": 402,
   "in_scope": 227,
   "inactive": 10
  },
  "product": "TWQR",
  "options": {
   "include_inactive_rules": false
  },
  "stage_by_table": {
   "yknBasicCheckValidation": "hard_reject",
   "yakeen-post-validation": "hard_reject",
   "simati_chk_IAF": "credit_policy",
   "racAndPolicies": "credit_policy"
  }
 },
 "dataset": {
  "available": true,
  "label": "Demo dataset (synthetic)",
  "rows": 50000,
  "columns": 36,
  "date_from": "1 Sep 2024",
  "date_to": "31 Aug 2026",
  "window_days": 730,
  "schema_problems": [],
  "nulls": [
   {
    "column": "military_rank",
    "share": 0.9212
   },
   {
    "column": "military_employee_type",
    "share": 0.9212
   },
   {
    "column": "simah_score",
    "share": 0.1638
   }
  ],
  "preview": {
   "columns": [
    "application_id",
    "app_date",
    "channel",
    "employer_segment",
    "monthly_income",
    "simah_score",
    "requested_amount",
    "tenure_months"
   ],
   "rows": [
    [
     "APP0000001",
     "2026-08-31",
     "branch",
     "GOV",
     13090.4,
     732.0,
     100000.0,
     60
    ],
    [
     "APP0000002",
     "2024-09-18",
     "digital",
     "GOV",
     7406.6,
     541.0,
     70000.0,
     60
    ],
    [
     "APP0000003",
     "2024-11-11",
     "digital",
     "PRIVATE_LARGE",
     5103.3,
     702.0,
     55000.0,
     60
    ],
    [
     "APP0000004",
     "2025-12-17",
     "digital",
     "PRIVATE_LARGE",
     8880.2,
     657.0,
     60000.0,
     36
    ],
    [
     "APP0000005",
     "2025-08-21",
     "branch",
     "SELF_EMPLOYED",
     8285.7,
     588.0,
     90000.0,
     36
    ],
    [
     "APP0000006",
     "2025-06-19",
     "digital",
     "PRIVATE_SMALL",
     2635.8,
     681.0,
     25000.0,
     72
    ]
   ]
  }
 },
 "fields": {
  "columns": [
   {
    "column": "employer_segment",
    "dtype": "string",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 197,
    "null_share": 0.0
   },
   {
    "column": "nationality",
    "dtype": "string",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 177,
    "null_share": 0.0
   },
   {
    "column": "program",
    "dtype": "string",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 135,
    "null_share": 0.0
   },
   {
    "column": "requested_amount",
    "dtype": "float64",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 107,
    "null_share": 0.0
   },
   {
    "column": "simah_score",
    "dtype": "float64",
    "nullable": true,
    "role": "rule input",
    "need": "Required",
    "rules": 102,
    "null_share": 0.1638
   },
   {
    "column": "employment_type",
    "dtype": "string",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 73,
    "null_share": 0.0
   },
   {
    "column": "monthly_income",
    "dtype": "float64",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 63,
    "null_share": 0.0
   },
   {
    "column": "age",
    "dtype": "int64",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 58,
    "null_share": 0.0
   },
   {
    "column": "employer_name",
    "dtype": "string",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 32,
    "null_share": 0.0
   },
   {
    "column": "military_rank",
    "dtype": "string",
    "nullable": true,
    "role": "rule input",
    "need": "Required",
    "rules": 31,
    "null_share": 0.9212
   },
   {
    "column": "crif_score",
    "dtype": "float64",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 25,
    "null_share": 0.0
   },
   {
    "column": "is_pensioner",
    "dtype": "bool",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 22,
    "null_share": 0.0
   },
   {
    "column": "simah_scorecard",
    "dtype": "string",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 17,
    "null_share": 0.0
   },
   {
    "column": "length_of_service_months",
    "dtype": "int64",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 14,
    "null_share": 0.0
   },
   {
    "column": "customer_type",
    "dtype": "string",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 10,
    "null_share": 0.0
   },
   {
    "column": "salary_to_bsf",
    "dtype": "string",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 10,
    "null_share": 0.0
   },
   {
    "column": "military_employee_type",
    "dtype": "string",
    "nullable": true,
    "role": "rule input",
    "need": "Required",
    "rules": 9,
    "null_share": 0.9212
   },
   {
    "column": "tenure_months",
    "dtype": "int64",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 9,
    "null_share": 0.0
   },
   {
    "column": "channel",
    "dtype": "string",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 1,
    "null_share": 0.0
   },
   {
    "column": "diplomatic_service",
    "dtype": "bool",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 1,
    "null_share": 0.0
   },
   {
    "column": "gender",
    "dtype": "string",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 1,
    "null_share": 0.0
   },
   {
    "column": "is_pep",
    "dtype": "bool",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 1,
    "null_share": 0.0
   },
   {
    "column": "payslip_age_months",
    "dtype": "int64",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 1,
    "null_share": 0.0
   },
   {
    "column": "related_to_pep",
    "dtype": "bool",
    "nullable": false,
    "role": "rule input",
    "need": "Required",
    "rules": 1,
    "null_share": 0.0
   },
   {
    "column": "walked_away",
    "dtype": "bool",
    "nullable": false,
    "role": "outcome",
    "need": "Needed for the funnel",
    "rules": 0,
    "null_share": 0.0
   },
   {
    "column": "agent_id",
    "dtype": "string",
    "nullable": false,
    "role": "analysis",
    "need": "Recommended",
    "rules": 0,
    "null_share": 0.0
   },
   {
    "column": "app_date",
    "dtype": "datetime64[ns]",
    "nullable": false,
    "role": "analysis",
    "need": "Recommended",
    "rules": 0,
    "null_share": 0.0
   },
   {
    "column": "application_id",
    "dtype": "string",
    "nullable": false,
    "role": "analysis",
    "need": "Recommended",
    "rules": 0,
    "null_share": 0.0
   },
   {
    "column": "bad_date",
    "dtype": "datetime64[ns]",
    "nullable": true,
    "role": "analysis",
    "need": "Recommended",
    "rules": 0,
    "null_share": 0.9861
   },
   {
    "column": "booking_date",
    "dtype": "datetime64[ns]",
    "nullable": true,
    "role": "analysis",
    "need": "Recommended",
    "rules": 0,
    "null_share": 0.7835
   },
   {
    "column": "downpayment_pct",
    "dtype": "float64",
    "nullable": false,
    "role": "analysis",
    "need": "Recommended",
    "rules": 0,
    "null_share": 0.0
   },
   {
    "column": "is_saudi",
    "dtype": "bool",
    "nullable": false,
    "role": "analysis",
    "need": "Recommended",
    "rules": 0,
    "null_share": 0.0
   },
   {
    "column": "product",
    "dtype": "string",
    "nullable": false,
    "role": "analysis",
    "need": "Recommended",
    "rules": 0,
    "null_share": 0.0
   },
   {
    "column": "sector",
    "dtype": "string",
    "nullable": false,
    "role": "analysis",
    "need": "Recommended",
    "rules": 0,
    "null_share": 0.0
   },
   {
    "column": "source_code",
    "dtype": "string",
    "nullable": false,
    "role": "analysis",
    "need": "Recommended",
    "rules": 0,
    "null_share": 0.0
   },
   {
    "column": "latent_bad",
    "dtype": "bool",
    "nullable": false,
    "role": "synthetic only",
    "need": "Not requested",
    "rules": 0,
    "null_share": 0.0
   }
  ],
  "required": 24,
  "required_mapped": 24,
  "unsupplied": [
   {
    "field": "count(simahtransform[item.ciinstallmentamount-item.originalinstallmentamount != 0]) > 0",
    "rules": 1
   }
  ]
 },
 "policy": {
  "appetite": [
   {
    "key": "Bad-rate ceiling",
    "value": 0.11,
    "fmt": "pct0",
    "help": "No recommended strategy may exceed this expected bad rate."
   },
   {
    "key": "Rule earns its place above",
    "value": 1.15,
    "fmt": "x2",
    "help": "A rule is keeping its place if the applicants it alone declines are at least this many times riskier than the booked book."
   },
   {
    "key": "Riskier swap-ins above",
    "value": 1.15,
    "fmt": "x2",
    "help": "Newly approved applicants above this multiple of the booked bad rate are called riskier."
   },
   {
    "key": "Safer swap-ins below",
    "value": 0.85,
    "fmt": "x2",
    "help": "Newly approved applicants below this multiple are called safer."
   }
  ],
  "model": [
   {
    "key": "Minimum group size",
    "value": 50,
    "fmt": "n0",
    "help": "A group smaller than this gets no risk estimate, however tempting."
   },
   {
    "key": "Minimum support coverage",
    "value": 0.7,
    "fmt": "pct0",
    "help": "Share of a group that must sit inside the booked score range."
   },
   {
    "key": "Minimum missing-score booked",
    "value": 200,
    "fmt": "n0",
    "help": "Applicants with no score are only estimated if the bank booked this many."
   }
  ],
  "portfolio": [
   {
    "key": "Over-exposed at",
    "value": 2.0,
    "fmt": "x1",
    "help": "A slice holding this multiple of an even split is flagged as concentrated."
   },
   {
    "key": "Under-exposed at",
    "value": 0.3,
    "fmt": "x1",
    "help": "A slice below this multiple of an even split is flagged as thin."
   },
   {
    "key": "Score bands",
    "value": [
     0,
     500,
     550,
     600,
     650,
     700,
     900
    ],
    "fmt": "list",
    "help": "Bureau score cut points used to slice the book."
   }
  ],
  "product": [
   {
    "key": "Product minimum amount (SAR)",
    "value": 3000,
    "fmt": "n0",
    "help": "Requests below this are declined by the product rules."
   },
   {
    "key": "Minimum acceptable offer",
    "value": 0.6,
    "fmt": "pct0",
    "help": "Share of the request an applicant will still accept."
   }
  ],
  "assumptions": [
   {
    "key": "A missing value satisfies a condition",
    "value": "No",
    "help": "16% of applicants have no bureau score and about 100 rules test it, so this one switch moves a lot of people."
   },
   {
    "key": "An applicant no rule catches",
    "value": "Approve",
    "help": "Whether an applicant no rule declines is approved or declined."
   },
   {
    "key": "Include inactive rules",
    "value": "No",
    "help": "The 10 inactive rules stay off, as in production."
   }
  ],
  "hard_reject_fields": [
   "employername",
   "politicallyexposedperson",
   "relatedtopep",
   "diplomaticservice"
  ],
  "hard_reject": [
   {
    "field": "employername",
    "label": "Restricted employer"
   },
   {
    "field": "politicallyexposedperson",
    "label": "Politically exposed person"
   },
   {
    "field": "relatedtopep",
    "label": "Related to a politically exposed person"
   },
   {
    "field": "diplomaticservice",
    "label": "Diplomatic service"
   }
  ],
  "levers": [
   {
    "field": "simahcreditscore",
    "from": 600,
    "to": 560,
    "label": "SIMAH cutoff down"
   },
   {
    "field": "simahcreditscore",
    "from": 600,
    "to": 580,
    "label": "SIMAH cutoff down"
   },
   {
    "field": "simahcreditscore",
    "from": 650,
    "to": 620,
    "label": "SIMAH 650 band down"
   },
   {
    "field": "crifscore",
    "from": 605,
    "to": 580,
    "label": "CRIF cutoff down"
   },
   {
    "field": "crifscore",
    "from": 571,
    "to": 545,
    "label": "CRIF 571 cutoff down"
   },
   {
    "field": "income",
    "from": 3500,
    "to": 3000,
    "label": "Minimum salary down"
   },
   {
    "field": "income",
    "from": 5000,
    "to": 4000,
    "label": "Low-income LOS band down"
   }
  ]
 },
 "run": {
  "available": true,
  "applicants": 50000,
  "rules_in_scope": 227,
  "rules_replayed": 226,
  "unevaluable": [
   "racAndPolicies#261"
  ],
  "never_fire": [
   {
    "rule_id": "racAndPolicies#002",
    "description": "Gov/ Semi Gov/ PVTL CRIF SCORE <= 605 and SIMAH SCORE <600"
   },
   {
    "rule_id": "racAndPolicies#003",
    "description": "Gov/ Semi Gov/ PVTL CRIF SCORE <= 571 and SIMAH SCORE >=600"
   },
   {
    "rule_id": "racAndPolicies#004",
    "description": "Retired CRIF SCORE <= 605 and SIMAH SCORE < 600"
   },
   {
    "rule_id": "racAndPolicies#005",
    "description": "Retired CRIF SCORE <= 571 and SIMAH SCORE >=600"
   },
   {
    "rule_id": "racAndPolicies#027",
    "description": "Minimum Income Saudi"
   },
   {
    "rule_id": "racAndPolicies#102",
    "description": "Customer Age (Hijri)"
   },
   {
    "rule_id": "racAndPolicies#103",
    "description": "Pensioner age at maturity > 75"
   },
   {
    "rule_id": "racAndPolicies#108",
    "description": "This rule applies when customer is Saudi, SIMAH score is between 600 and 99999, monthly in"
   }
  ],
  "never_fire_count": 16,
  "replay_seconds": 2.1,
  "generated": "2026-09-21 10:03 UTC"
 },
 "simulated": {
  "simulated": true,
  "licence": {
   "licensee": "Licensed bank",
   "licence_id": "TWQR-2026-0001",
   "issued_by": "Azentio licence service (offline signing)",
   "entitlements": [
    {
     "key": "Product",
     "value": "TWQR"
    },
    {
     "key": "Modules",
     "value": "Portfolio · Decline drivers · Simulator"
    },
    {
     "key": "Environments",
     "value": "Production · UAT"
    },
    {
     "key": "Named users",
     "value": "25"
    }
   ],
   "signature": {
    "algorithm": "Ed25519",
    "verified": true,
    "fingerprint": "9f2c 41ab 07de 5c18",
    "note": "Verified offline against the Azentio public key shipped with the product."
   },
   "ladder": [
    {
     "id": "active",
     "label": "Active",
     "from": "Start of term",
     "does": "Everything works.",
     "paused": []
    },
    {
     "id": "expiring",
     "label": "Expiring",
     "from": "1 Dec 2026",
     "does": "A banner and reminders to the named contacts. Everything still works.",
     "paused": []
    },
    {
     "id": "grace",
     "label": "Grace",
     "from": "1 Jan 2027",
     "does": "Everything still works. Daily reminders to administrators.",
     "paused": []
    },
    {
     "id": "read_only",
     "label": "Read-only",
     "from": "16 Jan 2027",
     "does": "Screens, analysis and export keep working. New data loads, configuration changes and recomputes are paused.",
     "paused": [
      "data.load",
      "rules.load",
      "recompute.run",
      "config.change"
     ]
    },
    {
     "id": "suspended",
     "label": "Suspended",
     "from": "15 Feb 2027",
     "does": "Analysis screens lock; this page and export stay open.",
     "paused": [
      "data.load",
      "rules.load",
      "recompute.run",
      "config.change",
      "analysis.view"
     ]
    }
   ],
   "always": [
    "Client data is never deleted.",
    "Export is never blocked."
   ],
   "scenarios": {
    "current": {
     "status": "active",
     "status_label": "Active",
     "does": "Everything works.",
     "term": "1 Sep 2026 to 31 Dec 2026",
     "valid_to": "31 Dec 2026",
     "headline": "Valid until 31 Dec 2026",
     "remaining": "101 days remaining",
     "chip": "Licence · valid to 31 Dec 2026",
     "paused": [],
     "renewed": false
    },
    "active": {
     "status": "active",
     "status_label": "Active",
     "does": "Everything works.",
     "term": "1 Sep 2026 to 31 Dec 2026",
     "valid_to": "31 Dec 2026",
     "headline": "Valid until 31 Dec 2026",
     "remaining": "100 days remaining",
     "chip": "Licence · valid to 31 Dec 2026",
     "paused": [],
     "renewed": false
    },
    "expiring": {
     "status": "expiring",
     "status_label": "Expiring",
     "does": "A banner and reminders to the named contacts. Everything still works.",
     "term": "1 Sep 2026 to 31 Dec 2026",
     "valid_to": "31 Dec 2026",
     "headline": "Valid until 31 Dec 2026",
     "remaining": "12 days remaining",
     "chip": "Licence · valid to 31 Dec 2026",
     "paused": [],
     "renewed": false
    },
    "grace": {
     "status": "grace",
     "status_label": "Grace",
     "does": "Everything still works. Daily reminders to administrators.",
     "term": "1 Sep 2026 to 31 Dec 2026",
     "valid_to": "31 Dec 2026",
     "headline": "Expired on 31 Dec 2026",
     "remaining": "6 days ago",
     "chip": "Licence · grace",
     "paused": [],
     "renewed": false
    },
    "read_only": {
     "status": "read_only",
     "status_label": "Read-only",
     "does": "Screens, analysis and export keep working. New data loads, configuration changes and recomputes are paused.",
     "term": "1 Sep 2026 to 31 Dec 2026",
     "valid_to": "31 Dec 2026",
     "headline": "Expired on 31 Dec 2026",
     "remaining": "25 days ago",
     "chip": "Licence · read-only",
     "paused": [
      "data.load",
      "rules.load",
      "recompute.run",
      "config.change"
     ],
     "renewed": false
    },
    "suspended": {
     "status": "suspended",
     "status_label": "Suspended",
     "does": "Analysis screens lock; this page and export stay open.",
     "term": "1 Sep 2026 to 31 Dec 2026",
     "valid_to": "31 Dec 2026",
     "headline": "Expired on 31 Dec 2026",
     "remaining": "60 days ago",
     "chip": "Licence · suspended",
     "paused": [
      "data.load",
      "rules.load",
      "recompute.run",
      "config.change",
      "analysis.view"
     ],
     "renewed": false
    },
    "renewed": {
     "status": "active",
     "status_label": "Active",
     "does": "Everything works.",
     "term": "1 Sep 2026 to 31 Mar 2027",
     "valid_to": "31 Mar 2027",
     "headline": "Valid until 31 Mar 2027",
     "remaining": "191 days remaining",
     "chip": "Licence · valid to 31 Mar 2027",
     "paused": [],
     "renewed": true
    }
   },
   "refresh": {
    "none": "No new licence found. The licence on file is unchanged.",
    "found": "A renewed licence file was found, verified and applied.",
    "apply": "The licence file was verified and applied.",
    "paused_message": "Paused under the current licence. Contact your administrator.",
    "how": "The deployed product has no outbound internet, so refresh does not ask a server whether payment arrived. It re-reads the licence store and re-verifies the signature. After payment Azentio issues a new signed licence file, delivered through the patch channel or applied here by an administrator."
   },
   "reminders": {
    "contacts": [
     "risk-admin@client-bank.example",
     "it-ops@client-bank.example"
    ],
    "notice_days": [
     90,
     60,
     30,
     7
    ]
   }
  },
  "connectors": {
   "types": [
    {
     "id": "oracle",
     "label": "Oracle Database",
     "driver": "python-oracledb (thin mode)",
     "default_port": 1521,
     "fields": [
      {
       "key": "host",
       "label": "Host",
       "type": "text",
       "required": true,
       "placeholder": "los-db.bank.internal"
      },
      {
       "key": "port",
       "label": "Port",
       "type": "number",
       "default": "1521"
      },
      {
       "key": "service",
       "label": "Service name",
       "type": "text",
       "required": true,
       "placeholder": "LOSPRD"
      },
      {
       "key": "schema",
       "label": "Schema",
       "type": "text",
       "placeholder": "LOS"
      },
      {
       "key": "tls",
       "label": "Transport security",
       "type": "select",
       "choices": [
        "TLS",
        "Wallet (mutual TLS)",
        "Off"
       ]
      }
     ]
    },
    {
     "id": "postgres",
     "label": "PostgreSQL",
     "driver": "psycopg 3",
     "default_port": 5432,
     "fields": [
      {
       "key": "host",
       "label": "Host",
       "type": "text",
       "required": true,
       "placeholder": "los-db.bank.internal"
      },
      {
       "key": "port",
       "label": "Port",
       "type": "number",
       "default": "5432"
      },
      {
       "key": "database",
       "label": "Database",
       "type": "text",
       "required": true,
       "placeholder": "los"
      },
      {
       "key": "schema",
       "label": "Schema",
       "type": "text",
       "default": "public"
      },
      {
       "key": "tls",
       "label": "Transport security",
       "type": "select",
       "choices": [
        "verify-full",
        "verify-ca",
        "require",
        "disable"
       ]
      }
     ]
    },
    {
     "id": "mysql",
     "label": "MySQL",
     "driver": "PyMySQL",
     "default_port": 3306,
     "fields": [
      {
       "key": "host",
       "label": "Host",
       "type": "text",
       "required": true,
       "placeholder": "los-db.bank.internal"
      },
      {
       "key": "port",
       "label": "Port",
       "type": "number",
       "default": "3306"
      },
      {
       "key": "database",
       "label": "Database",
       "type": "text",
       "required": true,
       "placeholder": "los"
      },
      {
       "key": "tls",
       "label": "Transport security",
       "type": "select",
       "choices": [
        "VERIFY_IDENTITY",
        "VERIFY_CA",
        "REQUIRED",
        "DISABLED"
       ]
      }
     ]
    }
   ],
   "auth": [
    {
     "id": "vault",
     "label": "Vault reference",
     "help": "Recommended. The credential lives in the bank's secrets store and is never typed into a browser."
    },
    {
     "id": "password",
     "label": "Username and password",
     "help": "For estates without a vault. Entered once and held server-side."
    }
   ],
   "extraction": {
    "objects": [
     "Table or view",
     "SQL query"
    ],
    "refresh": [
     "Manual",
     "Nightly",
     "Hourly"
    ],
    "read_only_note": "Use a read-only account. The product never writes to the source system."
   }
  },
  "connection_test": {
   "steps": [
    {
     "label": "Reach host",
     "detail": "Resolved and connected",
     "ms": 42
    },
    {
     "label": "Secure the channel",
     "detail": "Certificate chain accepted",
     "ms": 118
    },
    {
     "label": "Authenticate",
     "detail": "Service account accepted",
     "ms": 76
    },
    {
     "label": "Confirm read-only",
     "detail": "No write privileges found",
     "ms": 31
    },
    {
     "label": "Find the object",
     "detail": "Table located, 34 columns",
     "ms": 64
    },
    {
     "label": "Count rows",
     "detail": "Estimate returned",
     "ms": 210
    }
   ],
   "failures": {
    "host_missing": {
     "label": "Reach host",
     "detail": "No host was entered."
    },
    "port_invalid": {
     "label": "Reach host",
     "detail": "The port must be a number."
    },
    "required_missing": {
     "label": "Connection details",
     "detail": "A required field is empty."
    }
   },
   "done": "All checks passed. Live connections are not available in this environment."
  },
  "upload": {
   "data": "Loading a file is not available in this environment.",
   "rules": "Loading a rule pack is not available in this environment.",
   "accept_data": ".csv,.xlsx,.parquet",
   "accept_rules": ".xlsx"
  },
  "example_layout": {
   "source_object": "LOS.APPLICATIONS_V",
   "note": "An illustrative layout with bank-style column names, not your own schema.",
   "mapping": [
    {
     "column": "employer_segment",
     "source": "EMP_SEGMENT"
    },
    {
     "column": "nationality",
     "source": "NATIONALITY"
    },
    {
     "column": "program",
     "source": null
    },
    {
     "column": "requested_amount",
     "source": "REQ_AMT"
    },
    {
     "column": "simah_score",
     "source": "SIMAH_SCR"
    },
    {
     "column": "employment_type",
     "source": null
    },
    {
     "column": "monthly_income",
     "source": "TOT_INCOME"
    },
    {
     "column": "age",
     "source": "APPLICANT_AGE"
    },
    {
     "column": "employer_name",
     "source": "EMPLOYER_NM"
    },
    {
     "column": "military_rank",
     "source": null
    },
    {
     "column": "crif_score",
     "source": "CRIF_SCR"
    },
    {
     "column": "is_pensioner",
     "source": null
    },
    {
     "column": "simah_scorecard",
     "source": null
    },
    {
     "column": "length_of_service_months",
     "source": null
    },
    {
     "column": "customer_type",
     "source": null
    },
    {
     "column": "salary_to_bsf",
     "source": null
    },
    {
     "column": "military_employee_type",
     "source": null
    },
    {
     "column": "tenure_months",
     "source": "TENOR_M"
    },
    {
     "column": "channel",
     "source": "SRC_CHANNEL"
    },
    {
     "column": "diplomatic_service",
     "source": null
    },
    {
     "column": "gender",
     "source": "GENDER"
    },
    {
     "column": "is_pep",
     "source": null
    },
    {
     "column": "payslip_age_months",
     "source": null
    },
    {
     "column": "related_to_pep",
     "source": null
    },
    {
     "column": "walked_away",
     "source": null
    },
    {
     "column": "agent_id",
     "source": null
    },
    {
     "column": "app_date",
     "source": "APP_DT"
    },
    {
     "column": "application_id",
     "source": "APP_REF"
    },
    {
     "column": "bad_date",
     "source": null
    },
    {
     "column": "booking_date",
     "source": null
    },
    {
     "column": "downpayment_pct",
     "source": null
    },
    {
     "column": "is_saudi",
     "source": null
    },
    {
     "column": "product",
     "source": "PROD_CD"
    },
    {
     "column": "sector",
     "source": null
    },
    {
     "column": "source_code",
     "source": null
    }
   ],
   "summary": {
    "required": 24,
    "required_mapped": 11,
    "unmapped_required": [
     "program",
     "employment_type",
     "military_rank",
     "is_pensioner",
     "simah_scorecard",
     "length_of_service_months",
     "customer_type",
     "salary_to_bsf",
     "military_employee_type",
     "diplomatic_service",
     "is_pep",
     "payslip_age_months",
     "related_to_pep"
    ]
   }
  },
  "outcomes": {
   "note": "How a loan is classed as bad, and where its repayment history is read from.",
   "definition": [
    {
     "key": "A loan is bad when it reaches",
     "value": "90 days past due"
    },
    {
     "key": "Within",
     "value": "12 months on book"
    },
    {
     "key": "Only loans booked at least",
     "value": "12 months ago"
    },
    {
     "key": "Exclude",
     "value": "Early settlements and fraud cases"
    }
   ],
   "sources": [
    {
     "key": "Booked flag",
     "value": "LOAN_STATUS = 'DISBURSED'"
    },
    {
     "key": "Performance",
     "value": "COLLECTIONS.DPD_MAX_12M"
    },
    {
     "key": "Offer accepted",
     "value": "OFFER.ACCEPTED_FLAG"
    },
    {
     "key": "Bank's actual decision",
     "value": "DECISION.OUTCOME and DECISION.REASON_CD"
    }
   ],
   "reconciliation": "The bank's actual decision is compared with the replay, application by application, so a difference in the rules is found before it is found by a customer."
  },
  "governance": [
   {
    "group": "Deployment",
    "items": [
     {
      "key": "Environment",
      "value": "On-premise or private cloud"
     },
     {
      "key": "Data residency",
      "value": "In-kingdom. No outbound internet."
     }
    ]
   },
   {
    "group": "Access",
    "items": [
     {
      "key": "Sign-in",
      "value": "Single sign-on (OIDC or SAML)"
     },
     {
      "key": "Roles",
      "value": "Analyst · Risk approver · Administrator"
     },
     {
      "key": "Session",
      "value": "Server-side, 30-minute idle timeout"
     }
    ]
   },
   {
    "group": "Data protection",
    "items": [
     {
      "key": "Personal data",
      "value": "National ID and name masked; application ID hashed"
     },
     {
      "key": "Secrets",
      "value": "Held in the bank's vault; only references stored here"
     },
     {
      "key": "Retention",
      "value": "Extracts purged after 90 days"
     }
    ]
   },
   {
    "group": "Language model",
    "items": [
     {
      "key": "Provider",
      "value": "On-premise, OpenAI-compatible endpoint"
     },
     {
      "key": "Endpoint",
      "value": "https://llm.bank.internal/v1"
     },
     {
      "key": "Scope",
      "value": "Translates questions; never computes a figure"
     }
    ]
   }
  ],
  "regional": [
   {
    "key": "Language",
    "value": "English (Arabic available)"
   },
   {
    "key": "Currency",
    "value": "SAR"
   },
   {
    "key": "Time zone",
    "value": "Asia/Riyadh"
   },
   {
    "key": "Date format",
    "value": "Gregorian, with Hijri alongside"
   }
  ],
  "audit": [
   {
    "when": "Today 09:12",
    "who": "Risk admin",
    "what": "Applied licence file"
   },
   {
    "when": "Today 08:47",
    "who": "Analyst 2",
    "what": "Ran simulator: SIMAH cutoff 580"
   },
   {
    "when": "Yesterday 17:30",
    "who": "Risk admin",
    "what": "Loaded rule pack (4 workbooks)"
   },
   {
    "when": "Yesterday 16:05",
    "who": "Data engineer",
    "what": "Tested connection: Oracle (read-only)"
   },
   {
    "when": "Mon 11:20",
    "who": "Risk admin",
    "what": "Changed bad-rate ceiling 12% to 11%"
   }
  ],
  "versions": [
   {
    "key": "Application",
    "value": "1.4.0"
   },
   {
    "key": "Engine",
    "value": "2.2.1"
   },
   {
    "key": "Configuration",
    "value": "client-config r17 (preserved)"
   },
   {
    "key": "Last patch",
    "value": "1.3.2 to 1.4.0, applied 14 Sep 2026"
   },
   {
    "key": "Patch channel",
    "value": "Encrypted, signed by Azentio; up to date"
   }
  ],
  "recompute": {
   "steps": [
    "Load the applicant table",
    "Replay the rules",
    "Refit the risk model",
    "Score the scenario grid",
    "Search for strategies",
    "Write the results"
   ],
   "note": "Runs as a background job and takes a few minutes.",
   "done": "Recompute is not available in this environment. The figures are unchanged."
  },
  "diagnostics": {
   "bundle": "A bundle of logs, versions and configuration for Azentio support, with no applicant data in it. There is no remote access, so this is how a problem is reported.",
   "exports": [
    "Configuration (YAML)",
    "Audit log (CSV)"
   ],
   "results_exports": [
    "Decline drivers (CSV)",
    "Simulator scenarios (CSV)",
    "Portfolio report (PDF)"
   ],
   "note": "Export is available in every licence state."
  }
 }
};
