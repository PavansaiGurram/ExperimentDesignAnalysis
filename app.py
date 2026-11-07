"""Serve a local dashboard for the generated experiment results."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from generate_experiments import SEED, run


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
SCALE_USERS = {"starter": 100, "full": 5000}


def load_dashboard_data(data_dir: Path, users_per_experiment: int) -> dict[str, Any]:
    """Load exported experiment results, generating them if this is a fresh checkout."""
    dataset_path = data_dir / "dataset.json"
    summary_path = data_dir / "validation_summary.json"
    if not dataset_path.is_file() or not summary_path.is_file():
        run(data_dir, users_per_experiment=users_per_experiment, seed=SEED)

    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    experiments = {row["experiment_id"]: row for row in dataset["experiments"]}
    metrics = {row["metric_id"]: row for row in dataset["metric_definitions"]}
    plans = {row["experiment_id"]: row for row in dataset["experiment_metric_plans"]}
    results: dict[str, dict[str, dict[str, Any]]] = {}
    for result in dataset["experiment_results"]:
        results.setdefault(result["experiment_id"], {})[result["metric_id"]] = result

    experiment_rows = []
    for experiment_id, experiment in experiments.items():
        plan = plans[experiment_id]
        primary_id = plan["primary_metric_id"]
        primary_result = results.get(experiment_id, {}).get(primary_id)
        if primary_result is None:
            raise ValueError(f"Missing primary result for {experiment_id}")
        primary_metric = metrics[primary_id]
        guardrail = next(
            (
                metrics[metric_id]
                for metric_id in results.get(experiment_id, {})
                if metrics[metric_id]["role"] == "guardrail"
            ),
            None,
        )
        guardrail_result = (
            results[experiment_id].get(guardrail["metric_id"]) if guardrail else None
        )
        experiment_rows.append(
            {
                "experiment_id": experiment_id,
                "name": experiment["name"],
                "hypothesis": experiment["hypothesis"],
                "status": experiment["status"],
                "scenario": experiment["scenario"],
                "primary_metric": primary_metric["name"],
                "effect_direction": primary_metric["direction"],
                "result": primary_result,
                "guardrail": (
                    {
                        "name": guardrail["name"],
                        "status": guardrail_result["guardrail_status"],
                        "result_status": guardrail_result["result_status"],
                    }
                    if guardrail and guardrail_result
                    else None
                ),
            }
        )
    experiment_rows.sort(key=lambda row: row["experiment_id"])
    return {
        "summary": summary,
        "experiments": experiment_rows,
        "scale": data_dir.name,
    }


class DashboardHandler(BaseHTTPRequestHandler):
    dashboard_data: dict[str, Any]

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json({"status": "ok"})
        elif path == "/api/dashboard":
            self._send_json(self.dashboard_data)
        elif path == "/":
            self._send_file(WEB_ROOT / "index.html", "text/html; charset=utf-8")
        elif path == "/styles.css":
            self._send_file(WEB_ROOT / "styles.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self._send_file(
                WEB_ROOT / "app.js", "text/javascript; charset=utf-8"
            )
        else:
            self.send_error(404, "Not found")

    def _send_json(self, payload: Any) -> None:
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            self.send_error(500, "Dashboard asset is missing")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", choices=tuple(SCALE_USERS), default="starter")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    data_dir = ROOT / "generated" / args.scale
    try:
        dashboard_data = load_dashboard_data(data_dir, SCALE_USERS[args.scale])
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.exit(1, f"Could not load experiment data: {error}\n")

    handler = type(
        "ConfiguredDashboardHandler",
        (DashboardHandler,),
        {"dashboard_data": dashboard_data},
    )
    try:
        server = ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as error:
        parser.exit(1, f"Could not start dashboard at {args.host}:{args.port}: {error}\n")
    print(f"Dashboard ready at http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
