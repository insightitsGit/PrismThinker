import json
from pathlib import Path
from validation.analysis.fresh_report import report, flag_metrics
from validation.datasets.splitting import load_cases
from validation.schemas.result import Result, Action
from validation.schemas.case import Verdict


def test_extended_reporting_without_fresh_inference(tmp_path):
    cases=load_cases(Path(__file__).resolve().parents[1]/"datasets/processed/local-v0.1.1.jsonl")[:4]
    rows=[]
    for case in cases:
        sample=Result(case_id=case.case_id,system="sample",verdict=Verdict.APPROVE,action=Action.EXECUTE,confidence=.8,conflict=False)
        heads={name:{"evaluator":name,"verdict":"approve","confidence":.8,"backend":"rules"} for name in ["formal","policy"]}
        for name in ["single_local","self_consistency","majority_vote","llm_judge","prismthinker","eligibility_only"]:
            result=sample.model_copy(update={"system":name,"delta":.2,"raw":{"evaluators":heads,
                "samples":[sample.model_dump(mode="json")]*3,"aligned_delta":{"score":None,"sufficient_evidence":False},
                "conflict_signals":{"material_evidence_conflict":False,"policy_authority_conflict":False}}})
            rows.append({"case":case.model_dump(mode="json"),"result":result.model_dump(mode="json")})
    (tmp_path/"cases.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
    (tmp_path/"freeze.json").write_text("{}")
    data=report(tmp_path)
    assert data["prediction_cohorts"]["all_available"]["true_conflict"]["n"]==4
    assert data["prediction_cohorts"]["aligned_comparable"]["true_conflict"]["n"]==0
    assert data["engine_gate_action_agreement_count"]==4
    assert flag_metrics([True],[None])["fn"]==1
