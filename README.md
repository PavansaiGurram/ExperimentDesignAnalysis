# Experiment design and analysis workflow

This module provides an end-to-end, reproducible synthetic A/B experimentation
workflow: hypothesis and metric predeclaration, eligible audience generation,
fixed-seed assignment, exposure/conversion simulation, randomization checks,
guardrail analysis, uncertainty estimates, audit history, exception handling,
and data exports.

It uses Python's standard library only. It does not use external data or include
personal information.

## Run the dashboard

Python 3.10 or later is recommended. No third-party packages are required.
From the project folder in PowerShell:

```powershell
python app.py
```

Open [http://127.0.0.1:8081](http://127.0.0.1:8081). The app creates the
starter dataset on first run if it is missing, then serves a local dashboard
with primary results, confidence intervals, sample sizes, and guardrail
statuses. It uses synthetic data and binds to `127.0.0.1` by default. Stop it
with Ctrl+C.

Use the larger generated dataset with:

```powershell
python app.py --scale full
```

Choose another port with `python app.py --port 8082`. In VS Code, press F5 and
choose **Run experiment dashboard** to start the server and open the page.

## Generate data and run tests

To generate or regenerate the exports directly:

```powershell
python generate_experiments.py --scale starter --verify-reproducibility
python generate_experiments.py --scale full --verify-reproducibility
```

`starter` generates 1,000 audience members (100 per experiment); `full` (the
default) generates 50,000 (5,000 per experiment). Both scales use the same
generator, rules, scenario mix, and fixed seed (`20261022`). `--seed` changes
the seed; `--users-per-experiment N` overrides scale. Outputs default to
`generated/full` (ignored by Git to keep generated bulk data out of source
history). Use `--output-dir PATH` to select another destination.

`--verify-reproducibility` regenerates the data in a temporary directory and
compares checksums for every output file; a mismatch exits with an error.

## Output files

Every source and derived entity is exported as its own CSV. `dataset.json`
contains all input, event, audit, validation, and result tables, but not
ground-truth labels. `ground_truth.csv/json` is a separate evaluation-only
export. `schema.sql` defines SQLite tables and constraints; `seed.sql` includes
schema and non-ground-truth seed rows. `source_manifest.json` records the fixed
seed, generator version, synthetic provenance, and SHA-256 checksums.
`validation_summary.json` reports counts, integrity checks, SRM blocks,
guardrail results, and reproducibility status.

## Design and analysis rules

* Ten experiments each have a predeclared hypothesis, binary primary metric,
  binary support-contact guardrail, assignment unit, allocation, 14-day outcome
  window, confidence level, alpha, and SRM threshold.
* Every experiment includes control and treatment. One is deliberately
  unbalanced at 70/30; another has an actual 65/35 allocation despite its
  declared 50/50 plan to exercise SRM detection.
* Assignment is deterministic under the seed. Treatment effects apply to
  actually exposed treatment members; exposure noncompliance and missing
  exposure telemetry are represented separately.
* Effects are intention-to-treat: conversions are counted per randomized
  member inside the assignment-relative predeclared window. Post-window events
  are retained as events, flagged, and excluded. Ambiguous multi-variant
  members are excluded from both arms and explicitly counted.
* Binary effects are treatment-minus-control risk differences with standard
  errors, 95% Wald confidence intervals, and two-sided normal-approximation
  p-values. SRM uses a two-arm chi-square goodness-of-fit check; p < 0.001
  blocks causal interpretation. A lower-is-better guardrail fails only if the
  95% confidence interval's lower bound for adverse regression exceeds the
  predeclared 3 percentage-point allowance.
* Results use the metric-definition version active at analysis time. A later
  definition change is appended as a new version and audit event.
* Lifecycle and analyst decisions are append-only audit events. Intentional
  anomalies remain in source records and have derived issue records; evaluation
  labels and expected decisions are kept in the separate ground-truth export.

See [DATA_DICTIONARY.md](DATA_DICTIONARY.md) for all field constraints,
relationships, cardinalities, and exception handling. Run focused tests from
this project folder:

```powershell
python -m unittest discover -s tests -v
```

Verify the running app endpoints with `http://127.0.0.1:8081/health` and
`http://127.0.0.1:8081/api/dashboard`. The test suite also checks data loading,
first-run generation, HTTP routes, and the existing generator's integrity and
reproducibility behavior.

See [AI_DISCLOSURE.md](AI_DISCLOSURE.md) for the prompt history, AI-use
disclosure, review notes, and limitations. The repository currently has no
configured Git remote; publish it to a public GitHub repository from an
authorized account before treating that submission requirement as complete.
