"""Predeclared supplemental metrics for v1.2 fresh evaluation."""
import json
from pathlib import Path
from validation.analysis.prediction import aucs, signals
from validation.analysis.local_report import prediction_analysis
from validation.schemas.case import EvaluationCase
from validation.schemas.result import Result, Status
from prismthinker.config import EngineConfig
from prismthinker.core.schemas import EvaluatorResult
from prismthinker.core.contradiction import contradiction_matrix


def flag_metrics(gold, flags):
    pairs = [(g,p) for g,p in zip(gold,flags) if p is not None]
    tp=sum(g and p for g,p in pairs); fp=sum(not g and p for g,p in pairs)
    fn=sum(g and p is not True for g,p in zip(gold,flags))
    return {"n":len(pairs),"missing":len(gold)-len(pairs),"tp":tp,"fp":fp,"fn":fn,
            "precision":tp/(tp+fp) if tp+fp else None,"recall":tp/(tp+fn) if tp+fn else None,
            "f1":2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}


def report(output):
    output=Path(output)
    manifest=json.loads((output/"freeze.json").read_text())
    engine_config=EngineConfig.model_validate(manifest.get("engine_config",{}))
    rows=[json.loads(line) for line in (output/"cases.jsonl").read_text().splitlines()]
    cases_by_id={r["case"]["case_id"]:EvaluationCase.model_validate_json(json.dumps(r["case"])) for r in rows}
    cases=list(cases_by_id.values())
    systems={}
    for row in rows:
        r=Result.model_validate_json(json.dumps(row["result"]))
        systems.setdefault(r.system,{})[r.case_id]=r
    systems={name:[rs[c.case_id] for c in cases] for name,rs in systems.items()}
    operations={}
    for name,results in systems.items():
        acts=[r.action.value if r.status==Status.OK else None for r in results]
        expected=[c.ground_truth.acceptable_directives[0].value for c in cases]
        refusal=[x=="REFUSE" for x in expected]
        unnecessary_eligible=[c.ground_truth.answerable and not c.ground_truth.requires_human_review for c in cases]
        unnecessary=sum(a=="ESCALATE" and eligible for a,eligible in zip(acts,unnecessary_eligible))
        operations[name]={"refusal":flag_metrics(refusal,[a=="REFUSE" if a else None for a in acts]),
            "unnecessary_review_count":unnecessary,"unnecessary_review_denominator":sum(unnecessary_eligible),
            "unnecessary_review_rate":unnecessary/sum(unnecessary_eligible) if sum(unnecessary_eligible) else None,
            "directive_correct_count":sum(a==e for a,e in zip(acts,expected))}
    typed={}
    for name in ("prismthinker","eligibility_only"):
        typed[name]={key:flag_metrics([tag in c.metadata.tags for c in cases],
            [r.raw.get("conflict_signals",{}).get(key) if r.status==Status.OK else None for r in systems[name]])
            for key,tag in [("material_evidence_conflict","material-positive"),("policy_authority_conflict","authority-positive")]}
    records,_=prediction_analysis(cases,systems)
    components=["conclusion_conflict","evidence_conflict","premise_conflict","constraint_conflict","assumption_conflict"]
    for row,r in zip(records,systems["prismthinker"]):
        heads={k:EvaluatorResult.model_validate(v) for k,v in r.raw.get("evaluators",{}).items()}
        pairs,_=contradiction_matrix(heads,engine_config)
        row["scores"].update({"component:"+key:max((getattr(p.components,key) for p in pairs),default=None) for key in components})
        determined=[v for v in r.raw.get("evaluators",{}).values() if v["verdict"]!="undetermined"]
        simple=signals([v["verdict"] for v in determined],[v["confidence"] for v in determined])
        for key in ["binary_disagreement","dissent_count","confidence_spread","one_minus_majority_margin"]:
            row["scores"]["determined_heads:"+key]=simple[key] if simple else None
        aligned=r.raw.get("aligned_delta",{})
        row["scores"].update({"aligned_shadow":aligned.get("score"),
            "aligned_binary":float(aligned["contradictory_pairs"]>0) if aligned.get("sufficient_evidence") else None,
            "aligned_count":aligned.get("contradictory_pairs") if aligned.get("sufficient_evidence") else None})
    cohorts={}
    all_scores=[s for s in records[0]["scores"] if not s.startswith("aligned_")]
    for name,score_names in [("all_available",all_scores),("aligned_comparable",list(records[0]["scores"]))]:
        cohorts[name]={}
        for target in records[0]["targets"]:
            complete=[r for r in records if r["targets"][target] is not None and all(r["scores"][s] is not None for s in score_names)]
            cohorts[name][target]={"n":len(complete),"excluded":len(records)-len(complete),
                "scores":{s:aucs([r["targets"][target] for r in complete],[r["scores"][s] for r in complete]) for s in score_names}}
    agreement=sum(a.action==b.action for a,b in zip(systems["prismthinker"],systems["eligibility_only"]))
    data={"operations":operations,"typed_conflicts_engine_and_gate_only":typed,"prediction_cohorts":cohorts,
        "engine_gate_action_agreement_count":agreement,"case_count":len(cases),
        "limits":"Typed subtypes are only available for the engine/gate. Local models supply the common semantic union flag. Aligned score comparisons use one common comparable cohort; null is never replaced by zero. AUCs are point estimates, not superiority tests."}
    (output/"extended_metrics.json").write_text(json.dumps(data,indent=2,allow_nan=False),encoding="utf-8")
    (output/"extended_prediction_cases.jsonl").write_text("".join(json.dumps(r)+"\n" for r in records),encoding="utf-8")
    if any(c["n"] for c in cohorts["aligned_comparable"].values()):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        compared=cohorts["aligned_comparable"]
        names=["prism_delta","aligned_shadow","aligned_binary","aligned_count",
               "determined_heads:binary_disagreement","local_panel:binary_disagreement"]
        fig,axes=plt.subplots(1,len(compared),figsize=(18,5),sharey=True)
        for ax,(target,metrics) in zip(axes,compared.items()):
            for y,name in enumerate(names):
                value=metrics["scores"][name]["auroc"]
                if value is not None: ax.barh(y,value,color="#35618d")
            ax.set(title=target.replace("_"," "),xlabel="AUROC (unitless)",xlim=(0,1),yticks=range(len(names)),yticklabels=names)
            ax.axvline(.5,color="gray",linestyle="--")
            ax.text(.02,-.15,f"Common n={metrics['n']}; excluded={metrics['excluded']}",transform=ax.transAxes,fontsize=8)
        fig.suptitle("Aligned-score comparison: same comparable cases for every predictor")
        fig.text(.01,.01,"Source: frozen run, extended_metrics.json. Point estimates; no test-time score inversion or threshold fitting.",fontsize=8)
        fig.tight_layout(rect=(0,.04,1,.94))
        (output/"plots").mkdir(exist_ok=True)
        fig.savefig(output/"plots/aligned_auroc.png",dpi=180)
        plt.close(fig)
    return data
