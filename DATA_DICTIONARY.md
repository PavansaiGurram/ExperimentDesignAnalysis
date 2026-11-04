# Experiment workflow data dictionary

All records are synthetic; timestamps are UTC ISO-8601 strings. `NULL`/empty CSV
fields mean not applicable or unobserved, never zero. IDs are immutable and
zero-padded. `experiment_id` is `EXP-2026-000001`; variants are
`VAR-<experiment-id>-A/B`; assignments are
`ASG-<experiment-id>-<audience-member-id>` (the deliberate second assignment
uses the `-DUP01` suffix); exposure and conversion IDs are globally sequenced
`EXPOS-2026-000001` and `CONV-2026-000001`.

The generated SQLite schema (`schema.sql`) is the executable source for
types, foreign keys, uniqueness, and enum checks. The JSON and SQL seed exports
contain source, derived analysis, audit, and data-quality records. Ground truth
is exported separately and is deliberately absent from `dataset.json` and
`seed.sql`.

## Entities

`PK` means primary key; `FK` identifies the referenced table. Unless otherwise
stated, fields are required. Dates are inclusive when end dates are present.

### Experiment (`experiments`)

| Field | Type; required? | Allowed values / units | Uniqueness | Validation |
|---|---|---|---|---|
| `experiment_id` | string; yes | `EXP-2026-` + six digits | PK | Immutable, matches ID convention. |
| `name` | string; yes | Human-readable | None | Non-empty. |
| `hypothesis` | string; yes | Predeclared claim | None | Non-empty; never inferred from results. |
| `status` | enum; yes | `draft`, `randomized`, `collecting`, `completed`, `stopped` | None | Must agree with ordered audit history; generated data ends `completed`. |
| `randomization_unit` | enum; yes | `audience_member` | None | Must match assignment unit. |
| `planned_start_at` | UTC timestamp; yes | Timestamp | None | At or before `planned_end_at`. |
| `planned_end_at` | UTC timestamp; yes | Timestamp | None | Recruitment end; at or after start. |
| `analysis_at` | UTC timestamp; yes | Timestamp | None | Result calculation cutoff, fixed for reproducibility. |
| `planned_window_days` | integer; yes | Days, > 0 | None | Conversion window from each assignment. |
| `randomization_seed` | integer; yes | Non-negative | None | Seed used for the experiment's fixed-seed random stream. |
| `scenario` | enum-like string; yes | Named synthetic scenario | None | Documents intended coverage; not a user-level feature. |

### Variant (`variants`)

| Field | Type; required? | Allowed values / units | Uniqueness | Validation |
|---|---|---|---|---|
| `variant_id` | string; yes | `VAR-<experiment-id>-A/B` | PK; unique with experiment | Must reference its experiment. |
| `experiment_id` | string; yes | Experiment ID | FK | One experiment has two variants. |
| `variant_key` | enum; yes | `A`, `B` | Unique per experiment | `A` is control; `B` is treatment. |
| `name` | string; yes | `Control`, `Treatment` | None | Non-empty. |
| `allocation_probability` | real; yes | Probability (0, 1) | None | Probabilities sum to 1 per experiment. |
| `is_control` | boolean; yes | true/false | None | Exactly one control per experiment. |
| `configuration` | JSON string; yes | Treatment configuration | None | Valid JSON; synthetic, no personal data. |
| `effective_from` | UTC timestamp; yes | Timestamp | None | At or before `effective_to`. |
| `effective_to` | UTC timestamp; optional | Timestamp or NULL | None | NULL means still effective. |

### AudienceMember (`audience_members`)

| Field | Type; required? | Allowed values / units | Uniqueness | Validation |
|---|---|---|---|---|
| `audience_member_id` | string; yes | `USR-2026-` + six digits | PK; unique with experiment | Synthetic, deterministic ID. |
| `experiment_id` | string; yes | Experiment ID | FK | Membership belongs to one experiment. |
| `eligible` | boolean; yes | true/false | None | Only eligible members are randomized. |
| `eligibility_reason` | string; yes | Rule description | None | Must document eligibility decision. |
| `segment` | enum; yes | `consumer`, `small_business`, `enterprise` | None | Synthetic segment only. |
| `tenure_days` | integer; yes | Days, >= 0 | None | Non-negative. |
| `eligible_from` | UTC timestamp; yes | Timestamp | None | At or before `eligible_to`. |
| `eligible_to` | UTC timestamp; yes | Timestamp | None | Effective membership end. |

### Assignment (`assignments`)

| Field | Type; required? | Allowed values / units | Uniqueness | Validation |
|---|---|---|---|---|
| `assignment_id` | string; yes | `ASG-<experiment-id>-<user-id>` | PK | Exception duplicate uses deterministic `-DUP01` suffix. |
| `experiment_id` | string; yes | Experiment ID | FK | Must match the variant and audience member. |
| `variant_id` | string; yes | Variant ID | FK | Must belong to the same experiment. |
| `audience_member_id` | string; yes | Audience ID | FK | Must be eligible for the experiment. Normally one variant per member. |
| `assigned_at` | UTC timestamp; yes | Timestamp | None | In the experiment recruitment period; stable randomization record. |
| `assignment_probability` | real; yes | Probability (0, 1) | None | Probability used by the assignment draw; compared with declared allocation for SRM. |
| `assignment_status` | enum; yes | `assigned`, `revoked` | None | Historical state is not overwritten. |
| `is_exception_record` | boolean; yes | true/false | None | True only for deliberately injected duplicate assignment. |

### ExposureEvent (`exposure_events`)

| Field | Type; required? | Allowed values / units | Uniqueness | Validation |
|---|---|---|---|---|
| `exposure_id` | string; yes | `EXPOS-2026-` + six digits | PK | Immutable global counter. |
| `experiment_id` | string; yes | Experiment ID | FK | Must match linked assignment. |
| `assignment_id` | string; yes | Assignment ID | FK | One exposure opportunity per normal assignment; anomaly duplicate is intentionally unexposed. |
| `audience_member_id` | string; yes | Audience ID | FK | Must match linked assignment. |
| `variant_id` | string; yes | Variant ID | FK | Must match assigned variant. |
| `occurred_at` | UTC timestamp; yes | Timestamp | None | Normally at/after assignment; one labelled negative case precedes it. |
| `telemetry_status` | enum; yes | `observed`, `missing` | None | Missing telemetry has unknown exposure state. |
| `exposure_status` | enum; yes | `exposed`, `not_exposed`, `unknown` | None | Unknown iff telemetry is missing; non-exposure is noncompliance. |

### ConversionEvent (`conversion_events`)

| Field | Type; required? | Allowed values / units | Uniqueness | Validation |
|---|---|---|---|---|
| `conversion_id` | string; yes | `CONV-2026-` + six digits | PK | Immutable global counter. |
| `experiment_id` | string; yes | Experiment ID | FK | Must match assignment and metric. |
| `assignment_id` | string; yes | Assignment ID | FK | Event belongs to an assigned member. |
| `audience_member_id` | string; yes | Audience ID | FK | Must match assignment. |
| `metric_id` | string; yes | Metric ID | FK | Must be defined for this experiment. |
| `event_key` | string; yes | `activation`, `support_contact` | None | Matches metric definition. |
| `event_at` | UTC timestamp; yes | Timestamp | None | At/after assignment; metric counts it only within the predeclared window. |
| `value` | integer; yes | Binary 0/1 | None | Only value 1 events are emitted by this generator. |
| `event_status` | enum; yes | `observed`, `retracted` | None | Only observed events contribute to results. |

### MetricDefinition (`metric_definitions`)

| Field | Type; required? | Allowed values / units | Uniqueness | Validation |
|---|---|---|---|---|
| `metric_id` | string; yes | `MET-<experiment>-<metric>-V<n>` | PK | Immutable versioned ID. |
| `experiment_id` | string; yes | Experiment ID | FK | Metric belongs to one experiment. |
| `name` | string; yes | Metric name | Unique with experiment and version | Non-empty. |
| `metric_type` | enum; yes | `binary` | None | Binary event indicator. |
| `event_key` | string; yes | Event name | None | Must match conversion event key. |
| `aggregation` | enum; yes | `mean_of_binary` | None | Proportion of assigned members with a qualifying event. |
| `unit` | enum; yes | `proportion` | None | Range [0, 1]. |
| `direction` | enum; yes | `higher_is_better`, `lower_is_better` | None | Used for metric interpretation/guardrail. |
| `role` | enum; yes | `primary`, `guardrail` | None | Primary metric is selected in analysis plan. |
| `version` | integer; yes | Positive integer | Unique with experiment and name | Version is never overwritten. |
| `effective_from` | UTC timestamp; yes | Timestamp | None | At or before `effective_to`. |
| `effective_to` | UTC timestamp; optional | Timestamp or NULL | None | Later edits create a new metric row. |

### GuardrailMetric (`guardrail_metrics`)

| Field | Type; required? | Allowed values / units | Uniqueness | Validation |
|---|---|---|---|---|
| `guardrail_id` | string; yes | `GRD-<experiment>-<metric>-V<n>` | PK | Immutable. |
| `experiment_id` | string; yes | Experiment ID | FK | Must match metric. |
| `metric_id` | string; yes | Metric ID | FK; unique per experiment | Must reference a `guardrail` metric definition. |
| `max_regression` | real; yes | Proportion-point delta, >= 0 | None | A failure requires the 95% CI lower bound of adverse delta to exceed it. |
| `severity` | enum; yes | `warn`, `block_scale` | None | `block_scale` prevents scaling on a guardrail failure. |
| `effective_from` | UTC timestamp; yes | Timestamp | None | At or before end date. |
| `effective_to` | UTC timestamp; optional | Timestamp or NULL | None | Versioned history; no in-place change. |

### ExperimentResult (`experiment_results`)

| Field | Type; required? | Allowed values / units | Uniqueness | Validation |
|---|---|---|---|---|
| `result_id` | string; yes | `RES-2026-` + six digits | PK | One row per experiment and metric. |
| `experiment_id` | string; yes | Experiment ID | FK | Matches the analysis plan and metric. |
| `analysis_plan_id` | string; yes | Plan ID | FK | Plan was predeclared. |
| `metric_id` | string; yes | Metric ID | FK; unique per experiment | Result retains the exact metric version. |
| `analysis_population` | enum; yes | `intention_to_treat` | None | All unambiguous randomized assignments in denominator, including noncompliance. |
| `eligible_n` | integer; yes | Members | None | Equals control + treatment denominator after exclusions. |
| `excluded_assignment_n` | integer; yes | Assignment records | None | Ambiguous multi-variant member records are excluded. |
| `control_n`, `treatment_n` | integer; yes | Members | None | Denominators by randomized variant. |
| `control_events`, `treatment_events` | integer; yes | Binary events | None | Counts within the outcome window; cannot exceed denominator. |
| `control_rate`, `treatment_rate` | real; optional | Proportion [0, 1] | None | Events / denominator; NULL if denominator is zero. |
| `effect` | real; optional | Proportion points | None | Treatment minus control. |
| `standard_error` | real; optional | Proportion points | None | Independent-binomial Wald SE. |
| `ci_lower`, `ci_upper` | real; optional | Proportion points | None | 95% normal-approximation confidence interval. |
| `p_value` | real; optional | Probability [0, 1] | None | Two-sided normal-approximation test. |
| `srm_statistic` | real; yes | Chi-square statistic | None | Goodness-of-fit statistic vs declared allocation. |
| `srm_p_value` | real; yes | Probability [0, 1] | None | Two-arm chi-square p-value; below predeclared threshold blocks interpretation. |
| `guardrail_status` | enum; yes | `not_applicable`, `pass`, `fail`, `inconclusive` | None | Compared with the guardrail regression threshold and CI. |
| `result_status` | enum; yes | `evaluated`, `blocked_srm`, `guardrail_fail` | None | SRM blocks causal interpretation; guardrail failure is explicit. |
| `calculated_at` | UTC timestamp; yes | Timestamp | None | Results are append-only for the given metric version. |

### Supporting entities

`experiment_metric_plans` is a 1:1 bridge from `Experiment` to its predeclared
primary `MetricDefinition`; it stores ITT population, confidence, alpha, SRM
threshold, window, and plan version. `AuditEvent` is 1:N from `Experiment` and
appends lifecycle transitions and decisions (including the deliberately
recorded SRM-warning override). `DataQualityIssue` is a derived 1:N issue log;
it references a source entity by `(entity_type, entity_id)` and records the
detected rule and required action. `ground_truth.csv/json` is a separate
evaluation-only label file and has no join into input feature exports or SQL
seed data.

## Cardinality and join rules

* `Experiment` 1:N `Variant`, `AudienceMember`, `Assignment`,
  `MetricDefinition`, `GuardrailMetric`, `ExperimentResult`, `AuditEvent`, and
  `DataQualityIssue`.
* `Experiment` 1:1 `ExperimentMetricPlan`; the plan selects exactly one primary
  metric. `Experiment` N:M `MetricDefinition` through `GuardrailMetric` for
  declared guardrails; the plan is the primary-metric bridge.
* `AudienceMember` 1:N `Assignment` and `ConversionEvent` only through a
  specific experiment/assignment. A valid clean run has one assignment per
  member and experiment; deliberate duplicate assignments are detected and
  excluded rather than silently joined.
* `Variant` 1:N `Assignment`; `Assignment` 0:1 `ExposureEvent` and 0:N
  `ConversionEvent`. Events keep the referenced assignment and variant IDs.
* `MetricDefinition` 1:N `ConversionEvent`; `ExperimentResult` is one row per
  `(experiment, metric version)`.
* `DataQualityIssue` has an optional polymorphic source-record relationship;
  SQL-level FKs apply to its experiment, while the issue detector validates
  source entity IDs.

Analysis validates every foreign-key join, excludes all assignments for an
ambiguous member from both arms, treats missing conversions as zero only under
the documented complete-conversion-telemetry assumption, and excludes events
after the predeclared assignment-relative window. Exposure compliance is
descriptive only; the causal estimate remains ITT.
