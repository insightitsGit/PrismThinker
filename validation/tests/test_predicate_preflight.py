import json
from pathlib import Path
import pytest
from validation.datasets.splitting import load_cases
from validation.experiments.local_models import preflight_predicates

ROOT=Path(__file__).resolve().parents[1]


def test_initial_mapping_rejected_before_freeze():
    cases=load_cases(ROOT/"datasets/processed/adversarial-v0.2-L.jsonl")
    with pytest.raises(ValueError,match="preflight failed"): preflight_predicates(cases)


def test_applicability_syntax_is_checked_before_freeze():
    from validation.schemas.case import EvaluationCase
    case = load_cases(ROOT/"datasets/processed/adversarial-v0.2-L-syntax2.jsonl")[0]
    payload = case.model_dump(mode="json")
    payload["context"]["policy_rules"][0]["applies_when"] = "fact.requested === 1"
    changed = EvaluationCase.model_validate_json(json.dumps(payload))
    with pytest.raises(ValueError, match="applies_when"):
        preflight_predicates([changed])


def test_repair_preserves_cases_labels_and_accepts_grammar():
    old=load_cases(ROOT/"datasets/processed/adversarial-v0.2-L.jsonl")
    new=load_cases(ROOT/"datasets/processed/adversarial-v0.2-L-syntax2.jsonl")
    assert preflight_predicates(new)["predicate_errors"]==0
    for a,b in zip(old,new,strict=True):
        assert a.case_id==b.case_id
        assert a.ground_truth==b.ground_truth
        assert a.prompt==b.prompt
        assert a.evidence==b.evidence
        assert a.candidate_action==b.candidate_action
