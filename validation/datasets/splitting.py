import hashlib
import json
import random
from pathlib import Path
from validation.schemas.case import EvaluationCase, Source


def load_cases(path: Path) -> list[EvaluationCase]:
    cases = [EvaluationCase.model_validate_json(line) for line in
             path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not cases or len({c.case_id for c in cases}) != len(cases):
        raise ValueError("empty corpus or duplicate case IDs")
    return cases


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def split_cases(cases, seed=42, fractions=(0.6, 0.2, 0.2)):
    """Group-level 60/20/20; adversarial-containing groups reserved for test.

    If the requested test quota cannot contain them, fail instead of silently
    contaminating development or changing the requested allocation.
    """
    if len(fractions) != 3 or any(x < 0 for x in fractions) or abs(sum(fractions)-1) > 1e-9:
        raise ValueError("split fractions must be nonnegative and sum to one")
    groups = {}
    for case in cases:
        groups.setdefault(case.metadata.group_id, []).append(case)
    names = sorted(groups)
    n_cal = int(len(names) * fractions[0])
    n_val = int(len(names) * fractions[1])
    reserved = [g for g in names if any(c.metadata.source == Source.ADVERSARIAL for c in groups[g])]
    if len(reserved) > len(names) - n_cal - n_val:
        raise ValueError("adversarial groups exceed held-out quota")
    ordinary = [g for g in names if g not in reserved]
    random.Random(seed).shuffle(ordinary)
    partition = {"calibration": ordinary[:n_cal], "validation": ordinary[n_cal:n_cal+n_val],
                 "test": ordinary[n_cal+n_val:] + reserved}
    return {split: sorted(c.case_id for g in gs for c in groups[g]) for split, gs in partition.items()}
