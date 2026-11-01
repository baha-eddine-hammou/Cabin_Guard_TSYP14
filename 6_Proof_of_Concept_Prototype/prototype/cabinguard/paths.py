"""Repository locations, so datasets and paper outputs do not depend on where this package sits.

The repository is organised by deliverable; this package lives in
``6_Proof_of_Concept_Prototype/prototype``. Datasets stay in ``data/`` at the
repository root (git-ignored) and the paper's generated numbers go to
``1_IEEE_Research_Paper/``.
"""
from __future__ import annotations

from pathlib import Path

PROTOTYPE = Path(__file__).resolve().parents[1]


def _repo_root() -> Path:
    for p in PROTOTYPE.parents:
        if (p / "1_IEEE_Research_Paper").is_dir():
            return p
    return PROTOTYPE.parents[1]


REPO = _repo_root()
DATA = REPO / "data"
PAPER = REPO / "1_IEEE_Research_Paper"
