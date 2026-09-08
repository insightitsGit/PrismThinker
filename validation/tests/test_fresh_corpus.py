from pathlib import Path
from collections import Counter
from validation.datasets.splitting import load_cases
from validation.experiments.local_models import preflight_predicates

ROOT=Path(__file__).resolve().parents[1]


def test_fresh_corpus_representation_only():
    cases=load_cases(ROOT/"datasets/processed/fresh-v1.2-180.jsonl")
    old=load_cases(ROOT/"datasets/processed/adversarial-v0.2-L-syntax2.jsonl")
    assert len(cases)==180
    assert Counter(c.domain for c in cases)=={"agent_execution":60,"policy_compliance":60,"evidence_reasoning":60}
    assert len({c.metadata.group_id for c in cases})==30
    assert {c.case_id for c in cases}.isdisjoint(c.case_id for c in old)
    assert {c.prompt for c in cases}.isdisjoint(c.prompt for c in old)
    assert preflight_predicates(cases)["engine_evaluations"]==0
    assert any(c.context.get("causal_graph") for c in cases)
    assert any(c.context.get("objective") for c in cases)
    assert any(c.context.get("aligned_claims") for c in cases)
    for case in cases:
        expected=case.ground_truth.acceptable_directives[0].value
        assert case.ground_truth.safe_to_execute == (expected=="EXECUTE")
        assert case.ground_truth.requires_human_review == (expected=="ESCALATE")
        assert case.ground_truth.true_conflict == ("material-positive" in case.metadata.tags or "authority-positive" in case.metadata.tags)


def test_oracle_preserves_independent_refusal_and_historical_record_controls():
    cases=load_cases(ROOT/"datasets/processed/fresh-v1.2-180.jsonl")
    by_id={c.metadata.original_id:c for c in cases}
    assert by_id["independent_export_stop:0"].ground_truth.acceptable_directives[0].value=="REFUSE"
    assert by_id["dependent_export_stop:0"].ground_truth.acceptable_directives[0].value=="ESCALATE"
    assert by_id["outdated_numeric_evidence:0"].ground_truth.true_conflict is False
    assert by_id["opposing_process_paths:1"].ground_truth.acceptable_directives[0].value=="REFUSE"
    assert by_id["indirect_process_effect:4"].ground_truth.acceptable_directives[0].value=="GATHER"
