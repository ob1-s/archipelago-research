from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
for package in (ROOT / "constraint_forge_formation_v0", ROOT / "constraint_forge_behavioral_runner_v0"):
    if str(package) not in sys.path:
        sys.path.insert(0, str(package))
