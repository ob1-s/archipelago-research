from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
for package in (ROOT / "constraint_forge_behavioral_runner_r2._r2_world", ROOT / "constraint_forge_behavioral_runner_r2"):
    if str(package) not in sys.path:
        sys.path.insert(0, str(package))
