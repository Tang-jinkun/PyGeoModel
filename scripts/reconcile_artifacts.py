#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT if BACKEND_ROOT.is_dir() else PROJECT_ROOT))

from app.core.errors import AppError  # noqa: E402
from app.services.artifact_contracts import OUTPUT_CONTRACTS  # noqa: E402
from app.services.reconciliation import reconcile_all, repair_selected  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or explicitly repair task artifact manifests.")
    parser.add_argument("--verify-checksums", action="store_true")
    parser.add_argument("--upgrade-legacy", action="store_true")
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--model", choices=sorted(OUTPUT_CONTRACTS))
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.repair and (not args.model or not args.task_id):
        parser.error("--repair requires --model and at least one --task-id")
    try:
        if args.repair:
            repaired = repair_selected(args.model, args.task_id)
            payload: object = {"repaired_task_ids": repaired}
        else:
            report = reconcile_all(
                dry_run=not args.upgrade_legacy,
                verify_checksums=args.verify_checksums,
                upgrade_legacy=args.upgrade_legacy,
            )
            payload = [item.model_dump(mode="json") for item in report]
    except AppError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    elif isinstance(payload, list):
        for item in payload:
            print(f"{item['task_id']} {item['model_id']} {item['state']} {item.get('reason_code') or '-'} {item['action']}")
    else:
        print("repaired " + " ".join(payload["repaired_task_ids"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
