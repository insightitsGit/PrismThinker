import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from validation.datasets.splitting import load_cases, split_cases, digest
from validation.schemas.case import EvaluationCase, Verdict
from validation.schemas.result import Result, Status, Action
from validation.metrics import calculate
from validation.baselines.single_model import FixtureModel, SingleModel
from validation.baselines.majority_vote import MajorityVote
from validation.baselines.llm_judge import LLMJudge
from validation.prismthinker_eval.adapter import PrismThinkerAdapter
from validation.experiments.baseline_comparison import run

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cases():
    return load_cases(ROOT/"datasets/processed/local-v0.1.1.jsonl")


@pytest.mark.parametrize("field,value", [("safe_to_execute", "false"), ("true_conflict", 1),
                                           ("correct_verdict", "approve"), ("hard_veto", None)])
def test_strict_labels(cases, field, value):
    data = cases[0].model_dump(mode="json")
    data["ground_truth"][field] = value
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("value", [[], ["escalate"], ["ESCALATE", "ESCALATE"], [1]])
def test_strict_directive_annotations(cases, value):
    data = cases[0].model_dump(mode="json")
    data["ground_truth"]["acceptable_directives"] = value
    with pytest.raises(ValidationError): EvaluationCase.model_validate_json(json.dumps(data))


def test_annotation_upgrade_preserves_existing_labels(cases):
    legacy = load_cases(ROOT/"datasets/processed/local-v0.1.jsonl")
    for old, new in zip(legacy, cases, strict=True):
        before, after = old.model_dump(mode="json"), new.model_dump(mode="json")
        assert before["ground_truth"].pop("acceptable_directives") is None
        assert after["ground_truth"].pop("acceptable_directives")
        assert before == after
    assert split_cases(legacy) == split_cases(cases)


def test_strict_case_and_inputs(cases):
    data = cases[0].model_dump(mode="json")
    data["unexpected"] = True
    with pytest.raises(ValidationError): EvaluationCase.model_validate_json(json.dumps(data))
    del data["unexpected"]
    data["candidate_action"]["kind"] = "not-an-action"
    with pytest.raises(ValidationError): EvaluationCase.model_validate_json(json.dumps(data))
    assert "ground_truth" not in cases[0].system_input().model_dump()
    assert "metadata" not in cases[0].system_input().model_dump()


@pytest.mark.parametrize("mutation", [
    lambda d: d["candidate_action"].update(typo=True),
    lambda d: d["context"]["policy_rules"][0].update(severtiy="hard_veto"),
    lambda d: d["evidence"][0].update(trust="0.9"),
    lambda d: d["context"]["fact_specs"]["measured"].update(required="true"),
    lambda d: d["candidate_action"]["payload"].update(value=float("nan")),
])
def test_nested_input_rejection(cases, mutation):
    data = cases[0].model_dump(mode="json")
    mutation(data)
    with pytest.raises(ValidationError): EvaluationCase.model_validate_json(json.dumps(data))


def test_corpus_splits(cases):
    assert len(cases) == 60
    assert len({c.domain for c in cases}) == 3
    a = split_cases(cases)
    assert a == split_cases(list(reversed(cases)))
    assert [len(a[s]) for s in ("calibration", "validation", "test")] == [36,12,12]
    assignments = {cid: s for s, ids in a.items() for cid in ids}
    groups = {}
    for c in cases:
        groups.setdefault(c.metadata.group_id, set()).add(assignments[c.case_id])
        if c.metadata.source.value == "adversarial": assert assignments[c.case_id] == "test"
    assert all(len(s) == 1 for s in groups.values())
    assert split_cases(cases, seed=21) != a
    saved = json.loads((ROOT/"datasets/splits/local-v0.1.1.json").read_text())
    assert saved["splits"] == a
    assert saved["dataset_hash"] == digest([c.model_dump(mode="json") for c in cases])


def test_invalid_split(cases):
    with pytest.raises(ValueError): split_cases(cases, fractions=(.9,.1,0))
    with pytest.raises(ValueError): split_cases(cases, fractions=(.6,.2,.3))


def test_metrics(cases):
    safe = next(c for c in cases if c.metadata.group_id == "safe")
    unsafe = next(c for c in cases if c.metadata.group_id == "evidence")
    results = [Result(case_id=c.case_id, system="test", verdict=Verdict.APPROVE,
        action=Action.EXECUTE, conflict=False) for c in [safe,unsafe]]
    m = calculate([safe,unsafe], results)
    assert m["decision_accuracy"] == .5
    assert m["unsafe_action_rate"] == 1
    assert m["unsafe_action_count"] == 1
    assert m["autonomous_coverage"] == 1
    assert m["selective_accuracy"] == .5
    assert m["conflict_recall"] == 0
    assert m["conflict_f1"] == 0
    assert m["conflict_precision"] is None
    results[1] = Result(case_id=unsafe.case_id, system="test", status=Status.TIMEOUT, error="timed out")
    m = calculate([safe,unsafe], results)
    assert m["unsafe_action_rate"] == 0
    assert m["unsafe_action_rate_worst_case"] == 1
    assert m["decision_accuracy"] == .5
    assert m["autonomous_coverage"] == .5
    assert m["selective_accuracy"] == 1
    assert m["failures"] == 1
    assert m["estimated_cost_per_case_usd"] is None
    with pytest.raises(ValueError): calculate([safe,unsafe], results[:1])


def test_directive_accuracy_independent_of_verdict(cases):
    selected = [next(c for c in cases if c.metadata.group_id == g) for g in ["evidence", "missing", "safe"]]
    results = [Result(case_id=c.case_id, system="test", verdict=Verdict.UNDETERMINED,
        action=a) for c,a in zip(selected, [Action.ESCALATE, Action.GATHER, Action.EXECUTE])]
    metrics = calculate(selected, results)
    assert metrics["decision_accuracy"] == pytest.approx(1/3)
    assert metrics["directive_accuracy"] == 1
    assert metrics["verdict_mismatch_correct_directive_count"] == 2
    results[-1] = Result(case_id=selected[-1].case_id, system="test", status=Status.TIMEOUT)
    assert calculate(selected, results)["directive_accuracy"] == pytest.approx(2/3)
    selected[0] = selected[0].model_copy(deep=True)
    selected[0].ground_truth.acceptable_directives = [Action.ESCALATE, Action.GATHER]
    results[0].action = Action.GATHER
    assert calculate(selected, results)["directive_accuracy"] == pytest.approx(2/3)
    selected[0].ground_truth.acceptable_directives = None
    metrics = calculate(selected, results)
    assert metrics["directive_accuracy"] is None
    assert metrics["directive_annotation_missing_count"] == 1


def test_answer_directive_is_distinct(cases):
    case = cases[0].model_copy(deep=True)
    case.ground_truth.acceptable_directives = [Action.ANSWER]
    result = Result(case_id=case.case_id, system="test", verdict=Verdict.APPROVE, action=Action.EXECUTE)
    assert calculate([case], [result])["directive_accuracy"] == 0
    result.action = Action.ANSWER
    assert calculate([case], [result])["directive_accuracy"] == 1


def test_review_conflict_and_veto(cases):
    selected = [next(c for c in cases if c.metadata.group_id == g) for g in ["safe","evidence","veto"]]
    results = [Result(case_id=c.case_id, system="test", verdict=c.ground_truth.correct_verdict,
        action=Action.ESCALATE if i < 2 else Action.REFUSE, conflict=i==1, hard_veto=i==2,
        confident_consensus=i==1) for i,c in enumerate(selected)]
    m = calculate(selected, results)
    assert m["conflict_f1"] == 1
    assert m["human_review_precision"] == .5
    assert m["human_review_recall"] == 1
    assert m["unnecessary_escalation_rate"] == 1
    assert m["hard_veto_recall"] == 1
    assert m["false_consensus_rate"] == 1
    assert m["selective_accuracy"] is None


def test_baselines_and_roundtrip(cases):
    responses = json.loads((ROOT/"datasets/processed/mock-responses-v0.1.1.json").read_text())
    providers = [FixtureModel(responses, i) for i in range(3)]
    case = cases[0].system_input()
    for system in [SingleModel(providers[0]), MajorityVote(providers)]:
        result = system.evaluate(case)
        assert Result.model_validate_json(result.model_dump_json()) == result
        assert result.usage.calls in {1,3}
    tied = MajorityVote(providers[:2])
    responses[case.case_id][1]["verdict"] = "REJECT"
    assert tied.evaluate(case).action == Action.GATHER
    class FakeJudge:
        def judge(self, case, candidates): return providers[0].evaluate(case)
    judged = LLMJudge(providers, FakeJudge()).evaluate(case)
    assert judged.usage.calls == 4
    assert len(judged.raw["candidates"]) == 3


def test_partial_panel_retains_success_and_error(cases):
    class Good:
        def evaluate(self, case):
            return Result(case_id=case.case_id, system="good", verdict=Verdict.APPROVE, action=Action.EXECUTE)
    class Bad:
        def evaluate(self, case): raise TimeoutError("offline timeout")
    result = MajorityVote([Good(), Bad()]).evaluate(cases[0].system_input())
    assert result.status == Status.ERROR
    assert result.raw["samples"][0]["verdict"] == "APPROVE"
    assert result.raw["samples"][1]["status"] == "timeout"
    assert result.usage.estimated_cost_usd is None
    assert result.usage.calls is None


def test_malformed_response_retains_raw(cases):
    case = cases[0].system_input()
    raw = {"verdict": "unsupported", "confidence": .9, "reasoning": "invalid fixture"}
    result = SingleModel(FixtureModel({case.case_id: [raw]})).evaluate(case)
    assert result.status == Status.ERROR
    assert result.raw["response"] == raw
    assert result.usage.calls == 1


def test_adapter_public_api(cases):
    from prismthinker import PrismThinker
    from prismthinker.adapters.chorusgraph import to_chorusgraph
    case = next(c for c in cases if c.metadata.group_id == "veto").system_input()
    direct = PrismThinker().evaluate(case.reasoning_context())
    adapted = PrismThinkerAdapter().evaluate(case)
    assert adapted.action.value.lower() == to_chorusgraph(direct).directive.value
    assert adapted.delta == direct.contradiction_score
    assert adapted.hard_veto is True
    assert "evaluators" in adapted.raw


def make_config(tmp_path):
    config = json.loads((ROOT/"config/experiment.json").read_text())
    config.update(dataset=str(ROOT/"datasets/processed/local-v0.1.1.jsonl"),
                  responses=str(ROOT/"datasets/processed/mock-responses-v0.1.1.json"), output=str(tmp_path/"runs"))
    path = tmp_path/"experiment.json"
    path.write_text(json.dumps(config))
    return path, config


def test_end_to_end_and_manifest(tmp_path):
    path, config = make_config(tmp_path)
    out = run(path)
    manifest = json.loads((out/"manifest.json").read_text())
    assert manifest["state"] == "complete"
    assert manifest["config_hash"] == digest(manifest["effective_config"])
    assert len(manifest["source_hash"]) == 64
    rows = [json.loads(line) for line in (out/"cases.jsonl").read_text().splitlines()]
    assert len(rows) == 36
    assert all(Result.model_validate_json(json.dumps(row["result"])).status == Status.OK for row in rows)
    assert (out/"summary.md").exists()
    assert (out/"tables/overall.csv").exists()
    assert digest({"a":1,"b":2}) == digest({"b":2,"a":1})
    config["split"] = "test"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="locked"): run(path)


def test_failures_are_saved(tmp_path, monkeypatch):
    path, config = make_config(tmp_path)
    def fail(self, case): raise TimeoutError("fixture timeout")
    monkeypatch.setattr(SingleModel, "evaluate", fail)
    out = run(path)
    rows = [json.loads(line) for line in (out/"cases.jsonl").read_text().splitlines()]
    failed = [r for r in rows if r["result"]["system"] == "single_model_mock"]
    assert len(failed) == 12
    assert all(r["result"]["status"] == "timeout" for r in failed)
    assert json.loads((out/"metrics.json").read_text())["single_model_mock"]["overall"]["failures"] == 12
