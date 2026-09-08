import json
from pathlib import Path
import pytest
from validation.analysis.prediction import aucs, signals
from validation.baselines import ollama
from validation.experiments.local_models import Ledger, aggregate
from validation.schemas.case import CaseInput, Verdict, Action
from validation.schemas.result import Result, Status
from validation.datasets.splitting import load_cases
from validation.analysis.local_report import group_intervals, prediction_analysis


def sample_case():
    return CaseInput.model_validate_json(json.dumps({"case_id":"transport-only","domain":"test",
        "prompt":"Transport test: decide whether a permitted action should execute.","context":{},"evidence":[],
        "candidate_action":{"id":"test","name":"noop","kind":"tool_invocation","payload":{}}}))


def test_auc_known_values_and_ties():
    assert aucs([False,True],[.1,.9])["auroc"]==1
    assert aucs([False,True],[.9,.1])["auroc"]==0
    assert aucs([False,True],[.5,.5])["auroc"]==.5
    assert aucs([False,True],[.5,.5])["pr_auc"]==.5
    assert aucs([True,False,True],[.9,.8,.7])["pr_auc"]==pytest.approx(5/6)
    assert aucs([False,False],[.1,.5])["auroc"] is None
    with pytest.raises(ValueError): aucs([True],[])


def test_signals_orientation():
    unanimous=signals(["a"]*3,[.9,.9,.9])
    assert unanimous["one_minus_majority_margin"]==0
    mixed=signals(["a","a","b"],[.9,.8,.2])
    assert mixed["dissent_count"]==1
    assert mixed["confidence_spread"]==pytest.approx(.7)
    assert mixed["one_minus_majority_margin"]==pytest.approx(2/3)
    assert signals([None],[None]) is None


def test_ledger_no_retry_after_interruption(tmp_path):
    ledger=Ledger(tmp_path/"calls.jsonl")
    ledger.append({"event":"started","key":"x"})
    resumed=Ledger(tmp_path/"calls.jsonl")
    def forbidden(): raise AssertionError("must not retry")
    result=resumed.call("x","case","system",forbidden)
    assert result.status==Status.ERROR
    assert "unknown" in result.error
    assert Ledger(tmp_path/"calls.jsonl").call("x","case","system",forbidden)==result


def test_ledger_caches_exact_raw_output(tmp_path):
    result=Result(case_id="x",system="test",status=Status.ERROR,raw={"response":"bad json"})
    ledger=Ledger(tmp_path/"calls.jsonl")
    ledger.call("key","x","test",lambda:result)
    assert Ledger(tmp_path/"calls.jsonl").results["key"].raw==result.raw


def test_live_transport_schema_and_raw(monkeypatch):
    settings={"temperature":.6,"num_predict":256,"num_ctx":8192,"base_url":"http://127.0.0.1:11434","timeout_seconds":10}
    decision={"verdict":"APPROVE","action":"EXECUTE","confidence":.9,"conflict":False,"hard_veto":False,"reasoning":"Permitted."}
    response={"done":True,"done_reason":"stop","message":{"content":json.dumps(decision)},"prompt_eval_count":100,"eval_count":40}
    monkeypatch.setattr(ollama,"request_json",lambda *args:response)
    result=ollama.evaluate(sample_case(),"qwen3:4b",settings,42)
    assert result.status==Status.OK
    assert result.usage.input_tokens==100 and result.usage.output_tokens==40
    assert result.raw["request"]["think"] is False
    assert "ground_truth" not in result.raw["request"]["messages"][1]["content"]
    response["message"]["content"]="not json"
    result=ollama.evaluate(sample_case(),"qwen3:4b",settings,42)
    assert result.status==Status.ERROR and result.raw["response"]["message"]["content"]=="not json"


def test_remote_runtime_rejected():
    with pytest.raises(ValueError,match="loopback"): ollama.request_json("https://ollama.com","/api/tags")


def test_vote_action_separate_from_verdict():
    samples=[Result(case_id="x",system="s",verdict=v,action=Action.ESCALATE) for v in [Verdict.APPROVE,Verdict.REJECT,Verdict.CAUTION]]
    result=aggregate("x","vote",samples)
    assert result.action==Action.ESCALATE and result.verdict==Verdict.UNDETERMINED
    samples[0]=Result(case_id="x",system="s",status=Status.TIMEOUT)
    assert aggregate("x","vote",samples).status==Status.ERROR


def test_corpus_integrity_without_engine_execution():
    path=Path(__file__).resolve().parents[1]/"datasets/processed/adversarial-v0.2-L.jsonl"
    cases=load_cases(path)
    assert len(cases)==180
    assert len({c.metadata.group_id for c in cases})==30
    assert len({c.domain for c in cases})==3
    assert all(len(c.ground_truth.acceptable_directives)==1 for c in cases)
    assert all(c.metadata.source.value=="adversarial" for c in cases)
    assert any(c.ground_truth.safe_to_execute for c in cases)
    assert any(c.ground_truth.true_conflict for c in cases)
    assert any(not c.ground_truth.answerable for c in cases)
    assert all("oracle" not in c.system_input().model_dump_json() for c in cases)


def test_group_bootstrap_paired_determinism():
    cases=load_cases(Path(__file__).resolve().parents[1]/"datasets/processed/local-v0.1.1.jsonl")[:6]
    results=[Result(case_id=c.case_id,system="test",verdict=c.ground_truth.correct_verdict,action=c.ground_truth.acceptable_directives[0]) for c in cases]
    systems={"prismthinker":results,"same":results}
    a=group_intervals(cases,systems,100,.95,42)
    assert a==group_intervals(cases,systems,100,.95,42)
    assert a["paired_prism_minus_baseline"]["same"]["autonomous_coverage"]["low"]==0
