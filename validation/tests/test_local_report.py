import json
from pathlib import Path
from validation.datasets.splitting import load_cases
from validation.schemas.result import Result, Action
from validation.schemas.case import Verdict
from validation.analysis.local_report import report


def test_full_offline_report(tmp_path):
    # Pre-existing v0.1 fixtures only; never run the new evaluation set in tests.
    cases=load_cases(Path(__file__).resolve().parents[1]/"datasets/processed/local-v0.1.1.jsonl")[:10]
    rows=[]
    for case in cases:
        sample=Result(case_id=case.case_id,system="sample",verdict=Verdict.APPROVE,action=Action.EXECUTE,
                      confidence=.8,conflict=False)
        for name in ["single_local","self_consistency","majority_vote","llm_judge","prismthinker"]:
            result=sample.model_copy(update={"system":name,"delta":.2,
                "raw":{"samples":[sample.model_dump(mode="json")]*3,
                       "evaluators":{"head":{"verdict":"approve","confidence":.8}}}})
            rows.append({"case":case.model_dump(mode="json"),"result":result.model_dump(mode="json")})
    (tmp_path/"cases.jsonl").write_text("".join(json.dumps(row)+"\n" for row in rows))
    manifest={"study_id":"offline-test","group_count":5,"config":{"bootstrap_samples":100,
        "bootstrap_confidence":.95,"seed":42,"coverage_thresholds":[0,.9]}}
    (tmp_path/"freeze.json").write_text(json.dumps(manifest))
    report(tmp_path)
    assert (tmp_path/"plots/safety_coverage.png").stat().st_size>1000
    assert (tmp_path/"plots/prediction_auroc.png").stat().st_size>1000
    assert (tmp_path/"tables/prediction.csv").exists()
    metrics=json.loads((tmp_path/"metrics.json").read_text())
    assert metrics["prismthinker"]["overall"]["autonomous_coverage"]==1
