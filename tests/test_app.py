from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import urlopen

from app import DashboardHandler, load_dashboard_data
from generate_experiments import SEED, run
from http.server import ThreadingHTTPServer
from threading import Thread


class DashboardTests(unittest.TestCase):
    def test_loads_results_from_generated_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary) / "starter"
            run(data_dir, users_per_experiment=100, seed=SEED)
            dashboard = load_dashboard_data(data_dir, users_per_experiment=100)

        self.assertEqual(dashboard["scale"], "starter")
        self.assertEqual(len(dashboard["experiments"]), 10)
        first = dashboard["experiments"][0]
        self.assertEqual(first["name"], "Onboarding message")
        self.assertEqual(first["result"]["analysis_population"], "intention_to_treat")
        self.assertTrue(dashboard["summary"]["all_checks_passed"])
        self.assertNotIn("ground_truth", json.dumps(dashboard["experiments"]))

    def test_generates_data_when_directory_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary) / "starter"
            dashboard = load_dashboard_data(data_dir, users_per_experiment=10)
            self.assertTrue((data_dir / "dataset.json").is_file())
            self.assertEqual(len(dashboard["experiments"]), 10)

    def test_http_endpoints_serve_dashboard_assets_and_health(self) -> None:
        dashboard = {"summary": {"experiment_count": 1}, "experiments": []}
        handler = type(
            "TestDashboardHandler",
            (DashboardHandler,),
            {"dashboard_data": dashboard},
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            with urlopen(f"{base_url}/health") as response:
                self.assertEqual(json.load(response), {"status": "ok"})
            with urlopen(f"{base_url}/api/dashboard") as response:
                self.assertEqual(json.load(response), dashboard)
            with urlopen(base_url) as response:
                self.assertIn(b"Experiment Lab", response.read())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
