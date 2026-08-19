#!/usr/bin/env python3
"""Import an external GeoTIFF as an application-managed DEM COG."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT if BACKEND_ROOT.is_dir() else PROJECT_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.services.dem_store import import_dem_from_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a GeoTIFF DEM as a tiled COG dataset.")
    parser.add_argument("--source", required=True, type=Path, help="Path to the source GeoTIFF.")
    parser.add_argument("--dem-id", required=True, help="Stable DEM id, for example national-dem.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Override the application data directory; normally configured with PYGEOMODEL_DATA_DIR.",
    )
    args = parser.parse_args(argv)
    if args.data_dir is not None:
        settings.data_dir = args.data_dir.resolve()
    settings.ensure_directories()

    try:
        metadata = import_dem_from_path(args.source, args.dem_id)
    except AppError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(metadata.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
