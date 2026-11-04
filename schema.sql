PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'randomized', 'collecting', 'completed', 'stopped')),
    randomization_unit TEXT NOT NULL CHECK (randomization_unit = 'audience_member'),
    planned_start_at TEXT NOT NULL,
    planned_end_at TEXT NOT NULL,
    analysis_at TEXT NOT NULL,
    planned_window_days INTEGER NOT NULL CHECK (planned_window_days > 0),
    randomization_seed INTEGER NOT NULL CHECK (randomization_seed >= 0),
    scenario TEXT NOT NULL,
    CHECK (planned_start_at <= planned_end_at)
);

CREATE TABLE IF NOT EXISTS variants (
    variant_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    variant_key TEXT NOT NULL CHECK (variant_key IN ('A', 'B')),
    name TEXT NOT NULL,
    allocation_probability REAL NOT NULL CHECK (allocation_probability > 0 AND allocation_probability < 1),
    is_control INTEGER NOT NULL CHECK (is_control IN (0, 1)),
    configuration TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    UNIQUE (experiment_id, variant_key),
    UNIQUE (variant_id, experiment_id),
    CHECK (effective_to IS NULL OR effective_from <= effective_to)
);

CREATE TABLE IF NOT EXISTS audience_members (
    audience_member_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    eligible INTEGER NOT NULL CHECK (eligible IN (0, 1)),
    eligibility_reason TEXT NOT NULL,
    segment TEXT NOT NULL CHECK (segment IN ('consumer', 'small_business', 'enterprise')),
    tenure_days INTEGER NOT NULL CHECK (tenure_days >= 0),
    eligible_from TEXT NOT NULL,
    eligible_to TEXT NOT NULL,
    UNIQUE (audience_member_id, experiment_id),
    CHECK (eligible_from <= eligible_to)
);

CREATE TABLE IF NOT EXISTS assignments (
    assignment_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    variant_id TEXT NOT NULL,
    audience_member_id TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    assignment_probability REAL NOT NULL CHECK (assignment_probability > 0 AND assignment_probability < 1),
    assignment_status TEXT NOT NULL CHECK (assignment_status IN ('assigned', 'revoked')),
    is_exception_record INTEGER NOT NULL CHECK (is_exception_record IN (0, 1)),
    UNIQUE (assignment_id, experiment_id, audience_member_id, variant_id),
    UNIQUE (assignment_id, experiment_id, audience_member_id),
    FOREIGN KEY (variant_id, experiment_id) REFERENCES variants(variant_id, experiment_id),
    FOREIGN KEY (audience_member_id, experiment_id) REFERENCES audience_members(audience_member_id, experiment_id)
);

CREATE TABLE IF NOT EXISTS exposure_events (
    exposure_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    assignment_id TEXT NOT NULL,
    audience_member_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    telemetry_status TEXT NOT NULL CHECK (telemetry_status IN ('observed', 'missing')),
    exposure_status TEXT NOT NULL CHECK (exposure_status IN ('exposed', 'not_exposed', 'unknown')),
    FOREIGN KEY (assignment_id, experiment_id, audience_member_id, variant_id)
        REFERENCES assignments(assignment_id, experiment_id, audience_member_id, variant_id),
    CHECK ((telemetry_status = 'missing' AND exposure_status = 'unknown')
        OR (telemetry_status = 'observed' AND exposure_status IN ('exposed', 'not_exposed')))
);

CREATE TABLE IF NOT EXISTS metric_definitions (
    metric_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    name TEXT NOT NULL,
    metric_type TEXT NOT NULL CHECK (metric_type IN ('binary')),
    event_key TEXT NOT NULL,
    aggregation TEXT NOT NULL CHECK (aggregation = 'mean_of_binary'),
    unit TEXT NOT NULL CHECK (unit = 'proportion'),
    direction TEXT NOT NULL CHECK (direction IN ('higher_is_better', 'lower_is_better')),
    role TEXT NOT NULL CHECK (role IN ('primary', 'guardrail')),
    version INTEGER NOT NULL CHECK (version > 0),
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    UNIQUE (experiment_id, name, version),
    UNIQUE (metric_id, experiment_id),
    CHECK (effective_to IS NULL OR effective_from <= effective_to)
);

CREATE TABLE IF NOT EXISTS conversion_events (
    conversion_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    assignment_id TEXT NOT NULL,
    audience_member_id TEXT NOT NULL,
    metric_id TEXT NOT NULL,
    event_key TEXT NOT NULL,
    event_at TEXT NOT NULL,
    value INTEGER NOT NULL CHECK (value IN (0, 1)),
    event_status TEXT NOT NULL CHECK (event_status IN ('observed', 'retracted')),
    FOREIGN KEY (assignment_id, experiment_id, audience_member_id)
        REFERENCES assignments(assignment_id, experiment_id, audience_member_id),
    FOREIGN KEY (metric_id, experiment_id) REFERENCES metric_definitions(metric_id, experiment_id)
);

CREATE TABLE IF NOT EXISTS experiment_metric_plans (
    analysis_plan_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL UNIQUE REFERENCES experiments(experiment_id),
    primary_metric_id TEXT NOT NULL,
    analysis_population TEXT NOT NULL CHECK (analysis_population IN ('intention_to_treat')),
    confidence_level REAL NOT NULL CHECK (confidence_level > 0 AND confidence_level < 1),
    alpha REAL NOT NULL CHECK (alpha > 0 AND alpha < 1),
    srm_alpha REAL NOT NULL CHECK (srm_alpha > 0 AND srm_alpha < 1),
    window_days INTEGER NOT NULL CHECK (window_days > 0),
    predeclared_at TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    FOREIGN KEY (primary_metric_id, experiment_id)
        REFERENCES metric_definitions(metric_id, experiment_id)
);

CREATE TABLE IF NOT EXISTS guardrail_metrics (
    guardrail_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    metric_id TEXT NOT NULL,
    max_regression REAL NOT NULL CHECK (max_regression >= 0),
    severity TEXT NOT NULL CHECK (severity IN ('warn', 'block_scale')),
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    UNIQUE (experiment_id, metric_id),
    FOREIGN KEY (metric_id, experiment_id)
        REFERENCES metric_definitions(metric_id, experiment_id),
    CHECK (effective_to IS NULL OR effective_from <= effective_to)
);

CREATE TABLE IF NOT EXISTS experiment_results (
    result_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    analysis_plan_id TEXT NOT NULL REFERENCES experiment_metric_plans(analysis_plan_id),
    metric_id TEXT NOT NULL,
    analysis_population TEXT NOT NULL CHECK (analysis_population IN ('intention_to_treat')),
    eligible_n INTEGER NOT NULL CHECK (eligible_n >= 0),
    excluded_assignment_n INTEGER NOT NULL CHECK (excluded_assignment_n >= 0),
    control_n INTEGER NOT NULL CHECK (control_n >= 0),
    treatment_n INTEGER NOT NULL CHECK (treatment_n >= 0),
    control_events INTEGER NOT NULL CHECK (control_events >= 0 AND control_events <= control_n),
    treatment_events INTEGER NOT NULL CHECK (treatment_events >= 0 AND treatment_events <= treatment_n),
    control_rate REAL,
    treatment_rate REAL,
    effect REAL,
    standard_error REAL,
    ci_lower REAL,
    ci_upper REAL,
    p_value REAL,
    srm_statistic REAL NOT NULL,
    srm_p_value REAL NOT NULL CHECK (srm_p_value >= 0 AND srm_p_value <= 1),
    guardrail_status TEXT NOT NULL CHECK (guardrail_status IN ('not_applicable', 'pass', 'fail', 'inconclusive')),
    result_status TEXT NOT NULL CHECK (result_status IN ('evaluated', 'blocked_srm', 'guardrail_fail')),
    calculated_at TEXT NOT NULL,
    UNIQUE (experiment_id, metric_id),
    FOREIGN KEY (metric_id, experiment_id)
        REFERENCES metric_definitions(metric_id, experiment_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    audit_event_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT,
    actor TEXT NOT NULL,
    details TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS data_quality_issues (
    issue_id TEXT PRIMARY KEY,
    issue_type TEXT NOT NULL,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('medium', 'high', 'critical')),
    expected_action TEXT NOT NULL,
    observed_value TEXT NOT NULL,
    expected_value TEXT NOT NULL,
    detected_at TEXT NOT NULL
);
