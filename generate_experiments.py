"""Generate and analyze a reproducible synthetic experimentation program."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SEED = 20261022
GENERATOR_VERSION = "1.0.0"
ANALYSIS_DATE = date(2026, 6, 30)
WINDOW_DAYS = 14
ALPHA = 0.05
SRM_ALPHA = 0.001
TABLES = (
    "experiments",
    "variants",
    "audience_members",
    "assignments",
    "exposure_events",
    "metric_definitions",
    "experiment_metric_plans",
    "guardrail_metrics",
    "conversion_events",
    "experiment_results",
    "audit_events",
    "data_quality_issues",
)


def _experiment_id(number: int) -> str:
    return f"EXP-2026-{number:06d}"


def _stamp(value: date | datetime) -> str:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    return datetime.combine(value, datetime.min.time(), timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _scenario(number: int) -> dict[str, Any]:
    scenarios: dict[int, dict[str, Any]] = {
        1: {
            "name": "Onboarding message",
            "hypothesis": "A clearer onboarding message increases 14-day activation.",
            "control_allocation": 0.5,
            "assignment_control_probability": 0.5,
            "base_rate": 0.10,
            "treatment_effect": 0.025,
            "guardrail_effect": 0.0,
            "scenario": "balanced",
        },
        2: {
            "name": "Welcome offer",
            "hypothesis": "A welcome offer increases activation without excess support demand.",
            "control_allocation": 0.7,
            "assignment_control_probability": 0.7,
            "base_rate": 0.13,
            "treatment_effect": 0.015,
            "guardrail_effect": 0.0,
            "scenario": "unbalanced_allocation",
        },
        3: {
            "name": "Simplified checkout",
            "hypothesis": "A simplified checkout increases completed purchases.",
            "control_allocation": 0.5,
            "assignment_control_probability": 0.65,
            "base_rate": 0.09,
            "treatment_effect": 0.03,
            "guardrail_effect": 0.0,
            "scenario": "srm_warning_ignored",
        },
        4: {
            "name": "Reminder timing",
            "hypothesis": "A better-timed reminder increases timely conversion.",
            "control_allocation": 0.5,
            "assignment_control_probability": 0.5,
            "base_rate": 0.11,
            "treatment_effect": 0.02,
            "guardrail_effect": 0.0,
            "scenario": "delayed_conversion",
        },
        5: {
            "name": "Support shortcut",
            "hypothesis": "A support shortcut increases activation while monitoring contacts.",
            "control_allocation": 0.5,
            "assignment_control_probability": 0.5,
            "base_rate": 0.12,
            "treatment_effect": 0.025,
            "guardrail_effect": 0.18,
            "scenario": "guardrail_regression",
        },
        6: {
            "name": "Personalized landing page",
            "hypothesis": "A personalized landing page increases qualified sign-ups.",
            "control_allocation": 0.5,
            "assignment_control_probability": 0.5,
            "base_rate": 0.08,
            "treatment_effect": 0.035,
            "guardrail_effect": 0.0,
            "scenario": "multiple_variant_assignment",
        },
        7: {
            "name": "Product tour",
            "hypothesis": "An interactive product tour increases activation.",
            "control_allocation": 0.5,
            "assignment_control_probability": 0.5,
            "base_rate": 0.14,
            "treatment_effect": 0.02,
            "guardrail_effect": 0.0,
            "scenario": "exposure_before_assignment",
        },
        8: {
            "name": "Trial extension",
            "hypothesis": "A trial extension improves paid conversion.",
            "control_allocation": 0.5,
            "assignment_control_probability": 0.5,
            "base_rate": 0.07,
            "treatment_effect": 0.0,
            "guardrail_effect": 0.0,
            "scenario": "null_effect",
        },
        9: {
            "name": "Pricing page copy",
            "hypothesis": "Clearer pricing copy increases plan selection.",
            "control_allocation": 0.5,
            "assignment_control_probability": 0.5,
            "base_rate": 0.10,
            "treatment_effect": 0.04,
            "guardrail_effect": 0.0,
            "scenario": "metric_definition_change",
        },
        10: {
            "name": "Lead qualification form",
            "hypothesis": "A shorter form changes qualified lead completion.",
            "control_allocation": 0.5,
            "assignment_control_probability": 0.5,
            "base_rate": 0.12,
            "treatment_effect": -0.015,
            "guardrail_effect": 0.0,
            "scenario": "balanced_negative_effect",
        },
    }
    return scenarios[number]


def _round(value: float | None) -> float | None:
    return round(value, 8) if value is not None else None


def _new_dataset() -> dict[str, list[dict[str, Any]]]:
    return {table: [] for table in TABLES}


def build_dataset(users_per_experiment: int = 5000, seed: int = SEED) -> dict[str, list[dict[str, Any]]]:
    """Build source records, derive analyses, and label intentional exceptions."""
    if users_per_experiment < 2:
        raise ValueError("users_per_experiment must be at least 2")
    if seed < 0:
        raise ValueError("seed must be non-negative")

    data = _new_dataset()
    exposure_index = 0
    conversion_index = 0
    audience_index = 0
    metric_ids: dict[tuple[int, str], str] = {}
    assignment_by_experiment: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for experiment_number in range(1, 11):
        spec = _scenario(experiment_number)
        experiment_id = _experiment_id(experiment_number)
        start = date(2026, 1, 1) + timedelta(days=(experiment_number - 1) * 14)
        recruitment_end = start + timedelta(days=13)
        analysis_plan_id = f"PLAN-{experiment_id}-V1"
        primary_metric_id = f"MET-{experiment_id}-PRIMARY-V1"
        guardrail_metric_id = f"MET-{experiment_id}-SUPPORT-CONTACT-V1"
        metric_ids[(experiment_number, "primary")] = primary_metric_id
        metric_ids[(experiment_number, "guardrail")] = guardrail_metric_id

        data["experiments"].append(
            {
                "experiment_id": experiment_id,
                "name": spec["name"],
                "hypothesis": spec["hypothesis"],
                "status": "completed",
                "randomization_unit": "audience_member",
                "planned_start_at": _stamp(start),
                "planned_end_at": _stamp(
                    datetime.combine(
                        recruitment_end, datetime.max.time(), timezone.utc
                    )
                ),
                "analysis_at": _stamp(ANALYSIS_DATE),
                "planned_window_days": WINDOW_DAYS,
                "randomization_seed": seed + experiment_number * 1009,
                "scenario": spec["scenario"],
            }
        )
        for variant_key, allocation, is_control in (
            ("A", spec["control_allocation"], True),
            ("B", 1.0 - spec["control_allocation"], False),
        ):
            data["variants"].append(
                {
                    "variant_id": f"VAR-{experiment_id}-{variant_key}",
                    "experiment_id": experiment_id,
                    "variant_key": variant_key,
                    "name": "Control" if is_control else "Treatment",
                    "allocation_probability": allocation,
                    "is_control": is_control,
                    "configuration": json.dumps(
                        {"experience": "default" if is_control else "treatment"},
                        sort_keys=True,
                    ),
                    "effective_from": _stamp(start),
                    "effective_to": None,
                }
            )

        for metric_id, name, event_key, role, direction, unit in (
            (primary_metric_id, "14-day activation", "activation", "primary", "higher_is_better", "proportion"),
            (
                guardrail_metric_id,
                "Support contact rate",
                "support_contact",
                "guardrail",
                "lower_is_better",
                "proportion",
            ),
        ):
            data["metric_definitions"].append(
                {
                    "metric_id": metric_id,
                    "experiment_id": experiment_id,
                    "name": name,
                    "metric_type": "binary",
                    "event_key": event_key,
                    "aggregation": "mean_of_binary",
                    "unit": unit,
                    "direction": direction,
                    "role": role,
                    "version": 1,
                    "effective_from": _stamp(start),
                    "effective_to": _stamp(date(2026, 7, 1))
                    if experiment_number == 9
                    else None,
                }
            )
        data["experiment_metric_plans"].append(
            {
                "analysis_plan_id": analysis_plan_id,
                "experiment_id": experiment_id,
                "primary_metric_id": primary_metric_id,
                "analysis_population": "intention_to_treat",
                "confidence_level": 0.95,
                "alpha": ALPHA,
                "srm_alpha": SRM_ALPHA,
                "window_days": WINDOW_DAYS,
                "predeclared_at": _stamp(start),
                "version": 1,
            }
        )
        data["guardrail_metrics"].append(
            {
                "guardrail_id": f"GRD-{experiment_id}-SUPPORT-V1",
                "experiment_id": experiment_id,
                "metric_id": guardrail_metric_id,
                "max_regression": 0.03,
                "severity": "block_scale",
                "effective_from": _stamp(start),
                "effective_to": None,
            }
        )

        experiment_rng = random.Random(seed + experiment_number * 1009)
        for member_number in range(users_per_experiment):
            audience_index += 1
            audience_id = f"USR-2026-{audience_index:06d}"
            assigned_at = datetime.combine(
                start + timedelta(days=member_number % 14),
                datetime.min.time(),
                timezone.utc,
            ) + timedelta(seconds=member_number % 86400)
            segment = ("consumer", "small_business", "enterprise")[
                experiment_rng.randrange(3)
            ]
            data["audience_members"].append(
                {
                    "audience_member_id": audience_id,
                    "experiment_id": experiment_id,
                    "eligible": True,
                    "eligibility_reason": "consent_and_targeting_rules_met",
                    "segment": segment,
                    "tenure_days": experiment_rng.randrange(0, 730),
                    "eligible_from": _stamp(start),
                    "eligible_to": _stamp(
                        datetime.combine(
                            recruitment_end, datetime.max.time(), timezone.utc
                        )
                    ),
                }
            )

            assigned_control = (
                experiment_rng.random()
                < spec["assignment_control_probability"]
            )
            variant_key = "A" if assigned_control else "B"
            variant_id = f"VAR-{experiment_id}-{variant_key}"
            assignment_id = (
                f"ASG-{experiment_id}-{audience_id}"
            )
            assignment = {
                "assignment_id": assignment_id,
                "experiment_id": experiment_id,
                "variant_id": variant_id,
                "audience_member_id": audience_id,
                "assigned_at": _stamp(assigned_at),
                "assignment_probability": (
                    spec["assignment_control_probability"]
                    if assigned_control
                    else 1.0 - spec["assignment_control_probability"]
                ),
                "assignment_status": "assigned",
                "is_exception_record": False,
            }
            data["assignments"].append(assignment)
            assignment_by_experiment[experiment_number].append(assignment)

            actually_exposed = experiment_rng.random() < (
                0.95 if assigned_control else 0.91
            )
            telemetry_missing = experiment_rng.random() < 0.03
            exposure_index += 1
            data["exposure_events"].append(
                {
                    "exposure_id": f"EXPOS-2026-{exposure_index:06d}",
                    "experiment_id": experiment_id,
                    "assignment_id": assignment_id,
                    "audience_member_id": audience_id,
                    "variant_id": variant_id,
                    "occurred_at": _stamp(assigned_at + timedelta(hours=1)),
                    "telemetry_status": (
                        "missing" if telemetry_missing else "observed"
                    ),
                    "exposure_status": (
                        "unknown"
                        if telemetry_missing
                        else ("exposed" if actually_exposed else "not_exposed")
                    ),
                }
            )

            if assignment["assignment_status"] != "assigned":
                continue
            for metric_key, metric_id in (
                ("primary", primary_metric_id),
                ("guardrail", guardrail_metric_id),
            ):
                if metric_key == "primary":
                    probability = spec["base_rate"]
                    if not assigned_control and actually_exposed:
                        probability += spec["treatment_effect"]
                else:
                    probability = 0.12
                    if not assigned_control and actually_exposed:
                        probability += spec["guardrail_effect"]
                probability = min(max(probability, 0.001), 0.95)
                if experiment_rng.random() < probability:
                    delay_days = experiment_rng.randint(1, WINDOW_DAYS)
                    if experiment_number == 4 and experiment_rng.random() < 0.35:
                        delay_days = WINDOW_DAYS + experiment_rng.randint(1, 7)
                    conversion_index += 1
                    data["conversion_events"].append(
                        {
                            "conversion_id": f"CONV-2026-{conversion_index:06d}",
                            "experiment_id": experiment_id,
                            "assignment_id": assignment_id,
                            "audience_member_id": audience_id,
                            "metric_id": metric_id,
                            "event_key": (
                                "activation"
                                if metric_key == "primary"
                                else "support_contact"
                            ),
                            "event_at": _stamp(assigned_at + timedelta(days=delay_days)),
                            "value": 1,
                            "event_status": "observed",
                        }
                    )

    _inject_multiple_assignment(data, assignment_by_experiment[6])
    _inject_early_exposure(data, assignment_by_experiment[7])
    _inject_out_of_window_conversion(
        data, assignment_by_experiment[4], metric_ids[(4, "primary")]
    )
    if any(row["experiment_id"] == _experiment_id(9) for row in data["experiments"]):
        data["metric_definitions"].append(
            {
                "metric_id": f"MET-{_experiment_id(9)}-PRIMARY-V2",
                "experiment_id": _experiment_id(9),
                "name": "14-day activation (revised event semantics)",
                "metric_type": "binary",
                "event_key": "activation_v2",
                "aggregation": "mean_of_binary",
                "unit": "proportion",
                "direction": "higher_is_better",
                "role": "primary",
                "version": 2,
                "effective_from": _stamp(date(2026, 7, 1)),
                "effective_to": None,
            }
        )

    _calculate_results(data, metric_ids)
    _create_audit_history(data)
    _detect_issues(data)
    _create_ground_truth(data, metric_ids)
    return data


def _inject_multiple_assignment(
    data: dict[str, list[dict[str, Any]]], assignments: list[dict[str, Any]]
) -> None:
    source = assignments[0]
    duplicate = dict(source)
    duplicate["assignment_id"] = f"{source['assignment_id']}-DUP01"
    duplicate["variant_id"] = (
        f"VAR-{source['experiment_id']}-"
        + ("B" if source["variant_id"].endswith("-A") else "A")
    )
    duplicate["assigned_at"] = _stamp(
        datetime.fromisoformat(source["assigned_at"].replace("Z", "+00:00"))
        + timedelta(seconds=1)
    )
    duplicate["assignment_probability"] = 0.5
    duplicate["is_exception_record"] = True
    data["assignments"].append(duplicate)


def _inject_early_exposure(
    data: dict[str, list[dict[str, Any]]], assignments: list[dict[str, Any]]
) -> None:
    source = assignments[0]
    assignment_time = datetime.fromisoformat(
        source["assigned_at"].replace("Z", "+00:00")
    )
    data["exposure_events"].append(
        {
            "exposure_id": f"EXPOS-2026-{len(data['exposure_events']) + 1:06d}",
            "experiment_id": source["experiment_id"],
            "assignment_id": source["assignment_id"],
            "audience_member_id": source["audience_member_id"],
            "variant_id": source["variant_id"],
            "occurred_at": _stamp(assignment_time - timedelta(hours=1)),
            "telemetry_status": "observed",
            "exposure_status": "exposed",
        }
    )


def _inject_out_of_window_conversion(
    data: dict[str, list[dict[str, Any]]],
    assignments: list[dict[str, Any]],
    metric_id: str,
) -> None:
    source = assignments[0]
    assigned_at = datetime.fromisoformat(
        source["assigned_at"].replace("Z", "+00:00")
    )
    data["conversion_events"].append(
        {
            "conversion_id": f"CONV-2026-{len(data['conversion_events']) + 1:06d}",
            "experiment_id": source["experiment_id"],
            "assignment_id": source["assignment_id"],
            "audience_member_id": source["audience_member_id"],
            "metric_id": metric_id,
            "event_key": "activation",
            "event_at": _stamp(assigned_at + timedelta(days=WINDOW_DAYS + 1)),
            "value": 1,
            "event_status": "observed",
        }
    )


def _z_test(
    control_rate: float | None,
    treatment_rate: float | None,
    control_n: int,
    treatment_n: int,
) -> tuple[float | None, float | None, float | None, float | None]:
    if control_n == 0 or treatment_n == 0 or control_rate is None or treatment_rate is None:
        return None, None, None, None
    effect = treatment_rate - control_rate
    variance = (
        control_rate * (1.0 - control_rate) / control_n
        + treatment_rate * (1.0 - treatment_rate) / treatment_n
    )
    standard_error = math.sqrt(max(variance, 0.0))
    lower = effect - 1.96 * standard_error
    p_value = (
        math.erfc(abs(effect / standard_error) / math.sqrt(2.0))
        if standard_error > 0
        else (0.0 if effect else 1.0)
    )
    return effect, standard_error, lower, min(1.0, max(0.0, p_value))


def _srm_test(
    counts: dict[str, int], allocation: dict[str, float]
) -> tuple[float, float]:
    total = sum(counts.values())
    if total == 0:
        return 0.0, 1.0
    statistic = 0.0
    for variant, probability in allocation.items():
        expected = total * probability
        if expected == 0:
            return float("inf"), 0.0
        statistic += (counts.get(variant, 0) - expected) ** 2 / expected
    return statistic, math.erfc(math.sqrt(statistic / 2.0))


def _calculate_results(
    data: dict[str, list[dict[str, Any]]],
    metric_ids: dict[tuple[int, str], str],
) -> None:
    by_experiment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assignment in data["assignments"]:
        by_experiment[assignment["experiment_id"]].append(assignment)

    assignment_counts: Counter[str] = Counter()
    for assignment in data["assignments"]:
        assignment_counts[
            f"{assignment['experiment_id']}|{assignment['audience_member_id']}"
        ] += 1
    ambiguous_users = {
        pair for pair, count in assignment_counts.items() if count > 1
    }

    events_by_assignment_metric: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in data["conversion_events"]:
        events_by_assignment_metric[
            (event["assignment_id"], event["metric_id"])
        ].append(event)
    variant_by_id = {row["variant_id"]: row for row in data["variants"]}
    plan_by_experiment = {
        row["experiment_id"]: row for row in data["experiment_metric_plans"]
    }
    guardrail_by_metric = {
        row["metric_id"]: row for row in data["guardrail_metrics"]
    }
    result_index = 0

    for experiment_number in range(1, 11):
        experiment_id = _experiment_id(experiment_number)
        all_assignments = by_experiment[experiment_id]
        clean_assignments = [
            row
            for row in all_assignments
            if f"{experiment_id}|{row['audience_member_id']}" not in ambiguous_users
        ]
        counts = Counter(row["variant_id"] for row in clean_assignments)
        allocation = {
            row["variant_id"]: row["allocation_probability"]
            for row in data["variants"]
            if row["experiment_id"] == experiment_id
        }
        statistic, srm_p = _srm_test(counts, allocation)
        plan = plan_by_experiment[experiment_id]
        for metric_role in ("primary", "guardrail"):
            metric_id = metric_ids[(experiment_number, metric_role)]
            group_counts = {"A": 0, "B": 0}
            group_events = {"A": 0, "B": 0}
            for assignment in clean_assignments:
                variant = variant_by_id[assignment["variant_id"]]
                group = "A" if variant["is_control"] else "B"
                group_counts[group] += 1
                assigned_at = datetime.fromisoformat(
                    assignment["assigned_at"].replace("Z", "+00:00")
                )
                window_end = assigned_at + timedelta(days=plan["window_days"])
                if any(
                    datetime.fromisoformat(event["event_at"].replace("Z", "+00:00"))
                    <= window_end
                    and event["value"] == 1
                    and event["event_status"] == "observed"
                    for event in events_by_assignment_metric.get(
                        (assignment["assignment_id"], metric_id), []
                    )
                ):
                    group_events[group] += 1
            control_rate = (
                group_events["A"] / group_counts["A"] if group_counts["A"] else None
            )
            treatment_rate = (
                group_events["B"] / group_counts["B"] if group_counts["B"] else None
            )
            effect, standard_error, lower, p_value = _z_test(
                control_rate,
                treatment_rate,
                group_counts["A"],
                group_counts["B"],
            )
            upper = (
                effect + 1.96 * standard_error
                if effect is not None and standard_error is not None
                else None
            )
            guardrail_status = "not_applicable"
            if metric_id in guardrail_by_metric and effect is not None:
                threshold = guardrail_by_metric[metric_id]["max_regression"]
                if lower is not None and lower > threshold:
                    guardrail_status = "fail"
                elif upper is not None and upper <= threshold:
                    guardrail_status = "pass"
                else:
                    guardrail_status = "inconclusive"
            if srm_p < SRM_ALPHA:
                result_status = "blocked_srm"
            elif metric_role == "guardrail" and guardrail_status == "fail":
                result_status = "guardrail_fail"
            else:
                result_status = "evaluated"
            result_index += 1
            data["experiment_results"].append(
                {
                    "result_id": f"RES-2026-{result_index:06d}",
                    "experiment_id": experiment_id,
                    "analysis_plan_id": plan["analysis_plan_id"],
                    "metric_id": metric_id,
                    "analysis_population": plan["analysis_population"],
                    "eligible_n": len(all_assignments)
                    - sum(
                        1
                        for row in all_assignments
                        if f"{experiment_id}|{row['audience_member_id']}"
                        in ambiguous_users
                    ),
                    "excluded_assignment_n": len(all_assignments)
                    - len(clean_assignments),
                    "control_n": group_counts["A"],
                    "treatment_n": group_counts["B"],
                    "control_events": group_events["A"],
                    "treatment_events": group_events["B"],
                    "control_rate": _round(control_rate),
                    "treatment_rate": _round(treatment_rate),
                    "effect": _round(effect),
                    "standard_error": _round(standard_error),
                    "ci_lower": _round(lower),
                    "ci_upper": _round(upper),
                    "p_value": _round(p_value),
                    "srm_statistic": _round(statistic),
                    "srm_p_value": _round(srm_p),
                    "guardrail_status": guardrail_status,
                    "result_status": result_status,
                    "calculated_at": _stamp(ANALYSIS_DATE),
                }
            )


def _create_audit_history(data: dict[str, list[dict[str, Any]]]) -> None:
    audit_index = 0

    def add(
        experiment_id: str,
        event_type: str,
        event_at: date | datetime,
        from_state: str | None,
        to_state: str | None,
        actor: str,
        details: dict[str, Any],
    ) -> None:
        nonlocal audit_index
        audit_index += 1
        data["audit_events"].append(
            {
                "audit_event_id": f"AUD-2026-{audit_index:06d}",
                "experiment_id": experiment_id,
                "event_type": event_type,
                "occurred_at": _stamp(event_at),
                "from_state": from_state,
                "to_state": to_state,
                "actor": actor,
                "details": json.dumps(details, sort_keys=True),
            }
        )

    for number in range(1, 11):
        experiment_id = _experiment_id(number)
        start = date(2026, 1, 1) + timedelta(days=(number - 1) * 14)
        add(experiment_id, "lifecycle_transition", start, "draft", "randomized", "system", {})
        add(
            experiment_id,
            "lifecycle_transition",
            start + timedelta(days=1),
            "randomized",
            "collecting",
            "system",
            {},
        )
        add(
            experiment_id,
            "lifecycle_transition",
            ANALYSIS_DATE,
            "collecting",
            "completed",
            "analyst",
            {},
        )
    add(
        _experiment_id(3),
        "srm_warning_ignored",
        ANALYSIS_DATE - timedelta(days=1),
        None,
        None,
        "marketing_operations",
        {"action": "proceed_despite_srm_warning"},
    )
    add(
        _experiment_id(9),
        "metric_definition_changed",
        date(2026, 7, 1),
        None,
        None,
        "analyst",
        {
            "previous_metric_id": f"MET-{_experiment_id(9)}-PRIMARY-V1",
            "new_metric_id": f"MET-{_experiment_id(9)}-PRIMARY-V2",
        },
    )


def _detect_issues(data: dict[str, list[dict[str, Any]]]) -> None:
    issue_index = 0
    assignments_by_experiment_member: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    assignments_by_id = {row["assignment_id"]: row for row in data["assignments"]}
    for assignment in data["assignments"]:
        assignments_by_experiment_member[
            (assignment["experiment_id"], assignment["audience_member_id"])
        ].append(assignment)

    def add(
        issue_type: str,
        experiment_id: str,
        entity_type: str,
        entity_id: str,
        severity: str,
        expected_action: str,
        observed_value: str = "",
        expected_value: str = "",
    ) -> None:
        nonlocal issue_index
        issue_index += 1
        data["data_quality_issues"].append(
            {
                "issue_id": f"DQ-2026-{issue_index:06d}",
                "issue_type": issue_type,
                "experiment_id": experiment_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "severity": severity,
                "expected_action": expected_action,
                "observed_value": observed_value,
                "expected_value": expected_value,
                "detected_at": _stamp(ANALYSIS_DATE),
            }
        )

    for (experiment_id, member_id), rows in sorted(
        assignments_by_experiment_member.items()
    ):
        if len(rows) > 1:
            add(
                "multiple_variant_assignment",
                experiment_id,
                "AudienceMember",
                member_id,
                "high",
                "exclude_all_assignments_for_member",
                str(len(rows)),
                "1",
            )

    for event in data["exposure_events"]:
        assignment = assignments_by_id[event["assignment_id"]]
        if event["occurred_at"] < assignment["assigned_at"]:
            add(
                "exposure_before_assignment",
                event["experiment_id"],
                "ExposureEvent",
                event["exposure_id"],
                "high",
                "exclude_exposure_from_compliance_metrics",
                event["occurred_at"],
                assignment["assigned_at"],
            )

    for event in data["conversion_events"]:
        assignment = assignments_by_id[event["assignment_id"]]
        assigned_at = datetime.fromisoformat(
            assignment["assigned_at"].replace("Z", "+00:00")
        )
        event_at = datetime.fromisoformat(event["event_at"].replace("Z", "+00:00"))
        if event_at > assigned_at + timedelta(days=WINDOW_DAYS):
            add(
                "outcome_outside_predeclared_window",
                event["experiment_id"],
                "ConversionEvent",
                event["conversion_id"],
                "medium",
                "exclude_from_windowed_metric",
                event["event_at"],
                _stamp(assigned_at + timedelta(days=WINDOW_DAYS)),
            )

    results_by_experiment = defaultdict(list)
    for result in data["experiment_results"]:
        results_by_experiment[result["experiment_id"]].append(result)
    for number in range(1, 11):
        experiment_id = _experiment_id(number)
        result = next(
            row
            for row in results_by_experiment[experiment_id]
            if row["metric_id"] == f"MET-{experiment_id}-PRIMARY-V1"
        )
        if result["srm_p_value"] is not None and result["srm_p_value"] < SRM_ALPHA:
            counts = {
                variant["variant_key"]: sum(
                    1
                    for assignment in data["assignments"]
                    if assignment["experiment_id"] == experiment_id
                    and assignment["variant_id"] == variant["variant_id"]
                )
                for variant in data["variants"]
                if variant["experiment_id"] == experiment_id
            }
            add(
                "sample_ratio_mismatch",
                experiment_id,
                "ExperimentResult",
                result["result_id"],
                "critical",
                "block_causal_interpretation",
                json.dumps(counts, sort_keys=True),
                "declared_variant_allocation",
            )

    for event in data["audit_events"]:
        if event["event_type"] == "srm_warning_ignored":
            add(
                "sample_ratio_mismatch_ignored",
                event["experiment_id"],
                "AuditEvent",
                event["audit_event_id"],
                "critical",
                "block_causal_interpretation_and_escalate",
                event["details"],
                "stop_before_analysis",
            )
        elif event["event_type"] == "metric_definition_changed":
            add(
                "metric_definition_changed_after_result",
                event["experiment_id"],
                "AuditEvent",
                event["audit_event_id"],
                "high",
                "preserve_original_result_and_version",
                event["occurred_at"],
                _stamp(ANALYSIS_DATE),
            )


def _create_ground_truth(
    data: dict[str, list[dict[str, Any]]],
    metric_ids: dict[tuple[int, str], str],
) -> None:
    ground_truth: list[dict[str, Any]] = []
    issue_expectations = {
        "multiple_variant_assignment": (
            "exclude_ambiguous_member",
            "member_excluded_from_itt_denominator",
        ),
        "exposure_before_assignment": (
            "reject_exposure_event",
            "exposure_excluded_from_compliance",
        ),
        "outcome_outside_predeclared_window": (
            "exclude_conversion",
            "conversion_not_counted",
        ),
        "sample_ratio_mismatch": ("block_experiment", "blocked_srm"),
        "sample_ratio_mismatch_ignored": (
            "block_and_escalate",
            "blocked_srm",
        ),
        "metric_definition_changed_after_result": (
            "retain_versioned_result",
            "original_metric_version_retained",
        ),
    }
    for issue in data["data_quality_issues"]:
        action, expected = issue_expectations[issue["issue_type"]]
        ground_truth.append(
            {
                "ground_truth_id": f"GT-{issue['issue_id']}",
                "record_type": "known_exception",
                "experiment_id": issue["experiment_id"],
                "entity_type": issue["entity_type"],
                "entity_id": issue["entity_id"],
                "label": issue["issue_type"],
                "expected_decision": action,
                "expected_status": expected,
                "expected_value": "",
            }
        )

    for number in range(1, 11):
        spec = _scenario(number)
        experiment_id = _experiment_id(number)
        ground_truth.append(
            {
                "ground_truth_id": f"GT-{experiment_id}-EFFECT",
                "record_type": "synthetic_expectation",
                "experiment_id": experiment_id,
                "entity_type": "Experiment",
                "entity_id": experiment_id,
                "label": "designed_treatment_effect",
                "expected_decision": "compare_estimate_with_sampling_uncertainty",
                "expected_status": "effect_is_data_generating_parameter_not_guaranteed_observation",
                "expected_value": json.dumps(
                    {
                        "primary_effect_among_exposed": spec["treatment_effect"],
                        "guardrail_effect_among_exposed": spec["guardrail_effect"],
                        "primary_metric_id": metric_ids[(number, "primary")],
                    },
                    sort_keys=True,
                ),
            }
        )

    for status, label in (
        ("not_exposed", "treatment_noncompliance"),
        ("unknown", "missing_exposure_telemetry"),
    ):
        event = next(
            (
                row
                for row in data["exposure_events"]
                if row["experiment_id"] != _experiment_id(3)
                and row["exposure_status"] == status
                and row["variant_id"].endswith("-B")
            ),
            None,
        )
        if event is not None:
            ground_truth.append(
                {
                    "ground_truth_id": f"GT-{event['exposure_id']}-{label.upper()}",
                    "record_type": "coverage_example",
                    "experiment_id": event["experiment_id"],
                    "entity_type": "ExposureEvent",
                    "entity_id": event["exposure_id"],
                    "label": label,
                    "expected_decision": (
                        "retain_in_itt_and_mark_noncompliant"
                        if status == "not_exposed"
                        else "exclude_from_observed_exposure_rate"
                    ),
                    "expected_status": status,
                    "expected_value": "",
                }
            )
    data["ground_truth"] = ground_truth


def _validate_dataset(data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, valid: bool, detail: str) -> None:
        checks.append({"check": name, "passed": valid, "detail": detail})
        if not valid:
            errors.append(f"{name}: {detail}")

    primary_keys = {
        "experiments": "experiment_id",
        "variants": "variant_id",
        "audience_members": "audience_member_id",
        "assignments": "assignment_id",
        "exposure_events": "exposure_id",
        "conversion_events": "conversion_id",
        "metric_definitions": "metric_id",
        "experiment_metric_plans": "analysis_plan_id",
        "guardrail_metrics": "guardrail_id",
        "experiment_results": "result_id",
        "audit_events": "audit_event_id",
        "data_quality_issues": "issue_id",
        "ground_truth": "ground_truth_id",
    }
    for table, key in primary_keys.items():
        ids = [row[key] for row in data[table]]
        check(
            f"{table}_primary_key",
            len(ids) == len(set(ids)) and all(ids),
            f"{len(ids)} rows; unique non-empty {key}",
        )

    experiments = {row["experiment_id"]: row for row in data["experiments"]}
    variants = {row["variant_id"]: row for row in data["variants"]}
    members = {row["audience_member_id"]: row for row in data["audience_members"]}
    assignments = {row["assignment_id"]: row for row in data["assignments"]}
    metrics = {row["metric_id"]: row for row in data["metric_definitions"]}
    plans = {row["analysis_plan_id"]: row for row in data["experiment_metric_plans"]}
    fk_errors: list[str] = []
    for row in data["variants"]:
        if row["experiment_id"] not in experiments:
            fk_errors.append(f"variant {row['variant_id']}")
    for row in data["audience_members"]:
        if row["experiment_id"] not in experiments:
            fk_errors.append(f"audience member {row['audience_member_id']}")
    for row in data["assignments"]:
        if (
            row["experiment_id"] not in experiments
            or row["variant_id"] not in variants
            or row["audience_member_id"] not in members
            or variants[row["variant_id"]]["experiment_id"] != row["experiment_id"]
            or members[row["audience_member_id"]]["experiment_id"] != row["experiment_id"]
        ):
            fk_errors.append(f"assignment {row['assignment_id']}")
    for row in data["exposure_events"]:
        assignment = assignments.get(row["assignment_id"])
        if (
            assignment is None
            or row["audience_member_id"] not in members
            or row["variant_id"] not in variants
            or assignment["experiment_id"] != row["experiment_id"]
            or assignment["audience_member_id"] != row["audience_member_id"]
            or assignment["variant_id"] != row["variant_id"]
        ):
            fk_errors.append(f"exposure {row['exposure_id']}")
    for row in data["conversion_events"]:
        assignment = assignments.get(row["assignment_id"])
        if (
            assignment is None
            or row["metric_id"] not in metrics
            or row["audience_member_id"] not in members
            or assignment["experiment_id"] != row["experiment_id"]
            or assignment["audience_member_id"] != row["audience_member_id"]
            or metrics[row["metric_id"]]["experiment_id"] != row["experiment_id"]
        ):
            fk_errors.append(f"conversion {row['conversion_id']}")
    for row in data["experiment_metric_plans"]:
        if (
            row["experiment_id"] not in experiments
            or row["primary_metric_id"] not in metrics
            or metrics[row["primary_metric_id"]]["experiment_id"]
            != row["experiment_id"]
        ):
            fk_errors.append(f"plan {row['analysis_plan_id']}")
    for row in data["guardrail_metrics"]:
        if (
            row["experiment_id"] not in experiments
            or row["metric_id"] not in metrics
            or metrics[row["metric_id"]]["experiment_id"] != row["experiment_id"]
        ):
            fk_errors.append(f"guardrail {row['guardrail_id']}")
    for row in data["experiment_results"]:
        if (
            row["experiment_id"] not in experiments
            or row["analysis_plan_id"] not in plans
            or row["metric_id"] not in metrics
            or plans[row["analysis_plan_id"]]["experiment_id"]
            != row["experiment_id"]
            or metrics[row["metric_id"]]["experiment_id"] != row["experiment_id"]
        ):
            fk_errors.append(f"result {row['result_id']}")
    for row in data["audit_events"]:
        if row["experiment_id"] not in experiments:
            fk_errors.append(f"audit {row['audit_event_id']}")
    check("foreign_key_integrity", not fk_errors, f"{len(fk_errors)} invalid references")

    enum_errors: list[str] = []
    if any(row["status"] not in {"completed"} for row in data["experiments"]):
        enum_errors.append("experiment status")
    if any(row["variant_key"] not in {"A", "B"} for row in data["variants"]):
        enum_errors.append("variant key")
    if any(row["segment"] not in {"consumer", "small_business", "enterprise"} for row in data["audience_members"]):
        enum_errors.append("segment")
    if any(row["telemetry_status"] not in {"observed", "missing"} for row in data["exposure_events"]):
        enum_errors.append("telemetry status")
    if any(row["exposure_status"] not in {"exposed", "not_exposed", "unknown"} for row in data["exposure_events"]):
        enum_errors.append("exposure status")
    check("allowed_enums", not enum_errors, ", ".join(enum_errors) or "all enumerated values are allowed")

    issue_lookup = {
        (row["issue_type"], row["entity_id"])
        for row in data["data_quality_issues"]
    }
    date_errors: list[str] = []
    for row in data["experiments"]:
        if not (
            row["planned_start_at"] <= row["planned_end_at"] <= row["analysis_at"]
        ):
            date_errors.append(row["experiment_id"])
    for row in data["assignments"]:
        member = members[row["audience_member_id"]]
        if not member["eligible"]:
            date_errors.append(row["assignment_id"])
        if not (
            member["eligible_from"] <= row["assigned_at"] <= member["eligible_to"]
        ):
            date_errors.append(row["assignment_id"])
    for row in data["exposure_events"]:
        assignment = assignments[row["assignment_id"]]
        if (
            row["occurred_at"] < assignment["assigned_at"]
            and ("exposure_before_assignment", row["exposure_id"]) not in issue_lookup
        ):
            date_errors.append(row["exposure_id"])
    for row in data["conversion_events"]:
        assignment = assignments[row["assignment_id"]]
        if row["event_at"] < assignment["assigned_at"]:
            date_errors.append(row["conversion_id"])
        assigned_at = datetime.fromisoformat(
            assignment["assigned_at"].replace("Z", "+00:00")
        )
        event_at = datetime.fromisoformat(row["event_at"].replace("Z", "+00:00"))
        if (
            event_at > assigned_at + timedelta(days=WINDOW_DAYS)
            and (
                "outcome_outside_predeclared_window",
                row["conversion_id"],
            )
            not in issue_lookup
        ):
            date_errors.append(row["conversion_id"])
    check(
        "date_ordering_and_exception_labels",
        not date_errors,
        f"{len(date_errors)} invalid/unlabelled date-order records",
    )

    variant_probabilities: dict[str, float] = defaultdict(float)
    for row in data["variants"]:
        variant_probabilities[row["experiment_id"]] += row["allocation_probability"]
    check(
        "variant_allocation_reconciliation",
        all(abs(total - 1.0) < 1e-10 for total in variant_probabilities.values()),
        "each experiment has variant allocation probabilities summing to 1",
    )
    duplicate_groups: dict[tuple[str, str], int] = Counter(
        (row["experiment_id"], row["audience_member_id"])
        for row in data["assignments"]
    )
    declared_duplicate_groups = {
        (row["experiment_id"], row["entity_id"])
        for row in data["data_quality_issues"]
        if row["issue_type"] == "multiple_variant_assignment"
    }
    actual_duplicate_groups = {
        pair for pair, count in duplicate_groups.items() if count > 1
    }
    check(
        "duplicate_assignment_exception_is_labelled",
        actual_duplicate_groups == declared_duplicate_groups,
        f"{len(actual_duplicate_groups)} deliberate duplicate assignment group(s)",
    )

    result_errors: list[str] = []
    for result in data["experiment_results"]:
        if (
            result["control_n"] + result["treatment_n"] != result["eligible_n"]
            or result["control_events"] > result["control_n"]
            or result["treatment_events"] > result["treatment_n"]
        ):
            result_errors.append(result["result_id"])
        for group in ("control", "treatment"):
            denominator = result[f"{group}_n"]
            events = result[f"{group}_events"]
            rate = result[f"{group}_rate"]
            expected_rate = events / denominator if denominator else None
            if rate != _round(expected_rate):
                result_errors.append(result["result_id"])
    check(
        "result_arithmetic_reconciliation",
        not result_errors,
        f"{len(result_errors)} result rows fail count/rate reconciliation",
    )

    expected_transitions = [
        ("draft", "randomized"),
        ("randomized", "collecting"),
        ("collecting", "completed"),
    ]
    transition_errors = []
    for experiment_id in experiments:
        transitions = [
            (row["from_state"], row["to_state"])
            for row in data["audit_events"]
            if row["experiment_id"] == experiment_id
            and row["event_type"] == "lifecycle_transition"
        ]
        if transitions != expected_transitions:
            transition_errors.append(experiment_id)
    check(
        "lifecycle_transitions",
        not transition_errors,
        f"{len(transition_errors)} experiments have invalid lifecycle history",
    )

    expected_users = len(experiments) * (
        len(data["audience_members"]) // max(len(experiments), 1)
    )
    row_counts = {table: len(data[table]) for table in (*TABLES, "ground_truth")}
    summary = {
        "seed": None,
        "generator_version": GENERATOR_VERSION,
        "experiment_count": len(experiments),
        "eligible_audience_members": len(data["audience_members"]),
        "unique_assignment_users": len(
            {
                (row["experiment_id"], row["audience_member_id"])
                for row in data["assignments"]
            }
        ),
        "row_counts": row_counts,
        "checks": checks,
        "all_checks_passed": not errors,
        "result_status_counts": dict(
            Counter(row["result_status"] for row in data["experiment_results"])
        ),
        "guardrail_status_counts": dict(
            Counter(row["guardrail_status"] for row in data["experiment_results"])
        ),
        "issue_counts": dict(
            Counter(row["issue_type"] for row in data["data_quality_issues"])
        ),
        "exposure_status_counts": dict(
            Counter(row["exposure_status"] for row in data["exposure_events"])
        ),
        "telemetry_status_counts": dict(
            Counter(row["telemetry_status"] for row in data["exposure_events"])
        ),
        "expected_audience_count": expected_users,
    }
    if errors:
        raise ValueError("Dataset validation failed:\n- " + "\n- ".join(errors))
    return summary


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(
            {key: _csv_value(value) for key, value in row.items()} for row in rows
        )


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return "NULL"
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _refresh_manifest_hashes(output_dir: Path) -> None:
    manifest_path = output_dir / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = {
        path.name: _hash_file(path)
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path != manifest_path
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_sql(path: Path, data: dict[str, list[dict[str, Any]]], schema: str) -> None:
    statements = [
        "-- Generated deterministically by FDE/generate_experiments.py.",
        "PRAGMA foreign_keys = ON;",
        "BEGIN TRANSACTION;",
    ]
    for table in TABLES:
        rows = data[table]
        for row in rows:
            columns = ", ".join(row)
            values = ", ".join(_sql_literal(value) for value in row.values())
            statements.append(
                f"INSERT INTO {table} ({columns}) VALUES ({values});"
            )
    statements.append("COMMIT;")
    path.write_text(
        schema.rstrip() + "\n\n" + "\n".join(statements) + "\n",
        encoding="utf-8",
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_dataset(
    data: dict[str, list[dict[str, Any]]],
    output_dir: Path,
    seed: int = SEED,
    users_per_experiment: int = 5000,
) -> dict[str, Any]:
    """Write CSV, JSON, SQLite schema/seed SQL, and manifests."""
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = _validate_dataset(data)
    summary["seed"] = seed
    summary["users_per_experiment"] = users_per_experiment
    for table in TABLES:
        _write_csv(output_dir / f"{table}.csv", data[table])
    _write_csv(output_dir / "ground_truth.csv", data["ground_truth"])
    json_payload = {
        table: data[table] for table in TABLES
    }
    (output_dir / "dataset.json").write_text(
        json.dumps(json_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "ground_truth.json").write_text(
        json.dumps(data["ground_truth"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "validation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    project_root = Path(__file__).resolve().parent
    schema = (project_root / "schema.sql").read_text(encoding="utf-8")
    (output_dir / "schema.sql").write_text(schema, encoding="utf-8")
    _write_sql(output_dir / "seed.sql", data, schema)

    generated_files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name != "source_manifest.json"
    )
    manifest = {
        "generator": "FDE.generate_experiments",
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "users_per_experiment": users_per_experiment,
        "experiment_count": 10,
        "total_eligible_users": len(data["audience_members"]),
        "public_external_data_used": False,
        "source_manifest": [
            {
                "source": "synthetic_generator",
                "version": GENERATOR_VERSION,
                "seed": seed,
                "license": "synthetic; no third-party source data",
            }
        ],
        "sha256": {path.name: _hash_file(path) for path in generated_files},
    }
    (output_dir / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _verify_reproducibility(
    output_dir: Path, users_per_experiment: int, seed: int
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="fde-repro-") as temp_dir:
        second_dir = Path(temp_dir) / "second"
        second = build_dataset(users_per_experiment, seed)
        export_dataset(second, second_dir, seed, users_per_experiment)
        expected_files = {
            path.name: _hash_file(path)
            for path in output_dir.iterdir()
            if path.is_file()
        }
        second_files = {
            path.name: _hash_file(path)
            for path in second_dir.iterdir()
            if path.is_file()
        }
        same = expected_files == second_files
        if not same:
            changed = sorted(
                name
                for name in set(expected_files) | set(second_files)
                if expected_files.get(name) != second_files.get(name)
            )
            raise RuntimeError(f"Reproducibility check failed for: {changed}")
        return {
            "passed": True,
            "seed": seed,
            "files_compared": len(expected_files),
            "sha256_identical": True,
        }


def run(
    output_dir: Path,
    users_per_experiment: int = 5000,
    seed: int = SEED,
    verify_reproducibility: bool = False,
) -> dict[str, Any]:
    data = build_dataset(users_per_experiment, seed)
    summary = export_dataset(data, output_dir, seed, users_per_experiment)
    if verify_reproducibility:
        summary["reproducibility"] = _verify_reproducibility(
            output_dir, users_per_experiment, seed
        )
        (output_dir / "validation_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _refresh_manifest_hashes(output_dir)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate and analyze deterministic synthetic A/B experiments."
    )
    parser.add_argument(
        "--scale",
        choices=("starter", "full"),
        default="full",
        help="starter creates 1,000 members; full creates 50,000 (default)",
    )
    parser.add_argument(
        "--users-per-experiment",
        type=int,
        help="override scale (ten experiments are always generated)",
    )
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "generated" / "full",
    )
    parser.add_argument(
        "--verify-reproducibility",
        action="store_true",
        help="regenerate in a temporary directory and compare every output checksum",
    )
    args = parser.parse_args(argv)
    users = args.users_per_experiment
    if users is None:
        users = 100 if args.scale == "starter" else 5000
    summary = run(
        args.output_dir,
        users,
        args.seed,
        args.verify_reproducibility,
    )
    print(
        f"Generated {summary['eligible_audience_members']:,} eligible members "
        f"across {summary['experiment_count']} experiments."
    )
    print(f"Validation: {'PASS' if summary['all_checks_passed'] else 'FAIL'}")
    print(f"Outputs: {args.output_dir.resolve()}")
    if args.verify_reproducibility:
        print("Reproducibility: PASS (all output checksums match)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
