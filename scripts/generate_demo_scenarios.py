import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = (
    PROJECT_ROOT / "backend"
    if (PROJECT_ROOT / "backend").exists()
    else PROJECT_ROOT
)
sys.path.insert(0, str(BACKEND_ROOT))

from app.demo_scenarios.generator import main


if __name__ == "__main__":
    main()
