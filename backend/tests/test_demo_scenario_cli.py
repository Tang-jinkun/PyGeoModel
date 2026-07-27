import os
import subprocess
import sys
from pathlib import Path


def test_run_cli_exposes_required_options() -> None:
    project_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "run_demo_scenarios.py"),
            "--help",
        ],
        cwd=project_root,
        env={**os.environ, "PYTHONPATH": str(project_root / "backend")},
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--api-base-url" in result.stdout
    assert "--max-candidates" in result.stdout
    assert "--rebuild" in result.stdout
