import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = (
    PROJECT_ROOT / "backend"
    if (PROJECT_ROOT / "backend").exists()
    else PROJECT_ROOT
)
sys.path.insert(0, str(BACKEND_ROOT))

from app.demo_scenarios.api_client import DemoApiClient
from app.demo_scenarios.runner import run_scenarios


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run and validate synthetic PyGeoModel demo scenarios."
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--dem-id", required=True)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--max-candidates", type=int, default=4)
    parser.add_argument("--poll-seconds", type=float, default=2)
    parser.add_argument("--task-timeout-seconds", type=float, default=900)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    client = DemoApiClient(
        args.api_base_url,
        poll_seconds=args.poll_seconds,
        task_timeout_seconds=args.task_timeout_seconds,
    )
    index = run_scenarios(
        args.data_dir,
        args.dem_id,
        client,
        rebuild=args.rebuild,
        max_candidates=args.max_candidates,
    )
    print(json.dumps(index, ensure_ascii=False, indent=2))
    if not all(item.get("accepted") for item in index["models"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
