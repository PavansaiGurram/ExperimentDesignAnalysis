from __future__ import annotations

import json
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from generate_experiments import (
    SEED,
    _validate_dataset,
    build_dataset,
    run,
)


class ExperimentGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = build_dataset(users_per_experiment=1000, seed=SEED)

    def test_baseline_volume_and_validations(self) -> None:
        summary = _validate_dataset(self.data)
        self.assertEqual(len(self.data["experiments"]), 10)
        self.assertEqual(len(self.data["audience_members"]), 10_000)
        self.assertTrue(summary["all_checks_passed"])
        self.assertEqual(
            sum(row["eligible"] for row in self.data["audience_members"]), 10_000
        )

    def test_required_exceptions_are_explicit_and_decisions_are_safe(self) -> None:
        issue_types = {row["issue_type"] for row in self.data["data_quality_issues"]}
        self.assertTrue(
            {
                "multiple_variant_assignment",
                "exposure_before_assignment",
                "outcome_outside_predeclared_window",
                "sample_ratio_mismatch",
                "sample_ratio_mismatch_ignored",
                "metric_definition_changed_after_result",
            }.issubset(issue_types)
        )
        results = {
            (row["experiment_id"], row["metric_id"]): row
            for row in self.data["experiment_results"]
        }
        exp3 = "EXP-2026-000003"
        self.assertEqual(
            results[(exp3, f"MET-{exp3}-PRIMARY-V1")]["result_status"],
            "blocked_srm",
        )
        exp5 = "EXP-2026-000005"
        self.assertEqual(
            results[(exp5, f"MET-{exp5}-SUPPORT-CONTACT-V1")]["guardrail_status"],
            "fail",
        )
        self.assertEqual(
            results[(exp5, f"MET-{exp5}-SUPPORT-CONTACT-V1")]["result_status"],
            "guardrail_fail",
        )

    def test_estimates_reconcile_to_event_records(self) -> None:
        for result in self.data["experiment_results"]:
            self.assertEqual(
                result["control_n"] + result["treatment_n"], result["eligible_n"]
            )
            self.assertEqual(
                result["control_rate"],
                round(result["control_events"] / result["control_n"], 8)
                if result["control_n"]
                else None,
            )
            self.assertIsNotNone(result["standard_error"])
            self.assertIsNotNone(result["ci_lower"])
            self.assertIsNotNone(result["ci_upper"])

    def test_seed_sql_executes_and_ground_truth_is_not_seeded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            summary = run(output, users_per_experiment=100, seed=SEED)
            self.assertTrue(summary["all_checks_passed"])
            seed_sql = (output / "seed.sql").read_text(encoding="utf-8")
            self.assertNotIn("ground_truth", seed_sql.lower())
            with sqlite3.connect(":memory:") as connection:
                connection.executescript(seed_sql)
                count = connection.execute(
                    "SELECT COUNT(*) FROM audience_members"
                ).fetchone()[0]
                self.assertEqual(count, 1000)
                result_count = connection.execute(
                    "SELECT COUNT(*) FROM experiment_results"
                ).fetchone()[0]
                self.assertEqual(result_count, 20)
            dataset_json = json.loads(
                (output / "dataset.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("ground_truth", dataset_json)
            self.assertTrue((output / "ground_truth.csv").is_file())
            self.assertTrue((output / "ground_truth.json").is_file())

    def test_reproducibility_compares_export_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            run(output_dir, users_per_experiment=100, seed=SEED)
            summary = run(
                output_dir,
                users_per_experiment=100,
                seed=SEED,
                verify_reproducibility=True,
            )
            self.assertEqual(
                summary["reproducibility"],
                {
                    "passed": True,
                    "seed": SEED,
                    "files_compared": summary["reproducibility"]["files_compared"],
                    "sha256_identical": True,
                },
            )
            manifest = json.loads(
                (output_dir / "source_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["seed"], SEED)
            self.assertEqual(manifest["total_eligible_users"], 1000)
            summary_hash = hashlib.sha256(
                (output_dir / "validation_summary.json").read_bytes()
            ).hexdigest()
            self.assertEqual(
                manifest["sha256"]["validation_summary.json"], summary_hash
            )


if __name__ == "__main__":
    unittest.main()
