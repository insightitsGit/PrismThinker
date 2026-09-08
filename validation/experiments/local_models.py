"""Freeze once, run real local models with an append-only call ledger, report."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from time import perf_counter
import platform

from prismthinker import EngineConfig, __version__ as library_version
from validation.schemas.case import EvaluationCase, Verdict, Action
from validation.schemas.result import Result, Status, Usage
from validation.datasets.splitting import load_cases, digest
from validation.experiments.baseline_comparison import source_hash, git
from validation.baselines.ollama import request_json, evaluate, PROMPT, JUDGE_PROMPT
from validation.prismthinker_eval.adapter import PrismThinkerAdapter
from validation.baselines.majority_vote import MajorityVote


def preflight_predicates(cases):
    """Validate the representation contract, never call the reasoning engine.

    Syntax/type errors invalidate the corpus. Unbound required facts are deliberate
    missing-evidence cases and remain allowed; nothing is relabeled.
    """
    from prismthinker.core.predicates import evaluate_predicate
    problems=[]
    for case in cases:
        context=case.system_input().reasoning_context()
        for rule in [*context.policy_rules, *context.constraints]:
            expressions = [("predicate", rule.predicate)]
            if getattr(rule, "applies_when", None):
                expressions.append(("applies_when", rule.applies_when))
            for field, expression in expressions:
                value=evaluate_predicate(expression,context.structured_facts,context.hypothesis.action)
                if value.error and not value.unbound:
                    problems.append({"case_id":case.case_id,"rule_id":rule.id,"field":field,"error":value.error})
    if problems:
        raise ValueError(f"input predicate preflight failed: {len(problems)} invalid rules; first: {problems[0]}")
    return {"case_count":len(cases),"predicate_errors":0,"engine_evaluations":0}


def write_json(path, value): path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding="utf-8")


def freeze(config_path):
    path = Path(config_path).resolve()
    config = json.loads(path.read_text(encoding="utf-8"))
    cases = load_cases(path.parent/config["dataset"])
    preflight=preflight_predicates(cases)
    if len(cases)<150 or len({c.domain for c in cases})<3: raise ValueError("study needs 150+ cases and three domains")
    if any(c.ground_truth.acceptable_directives is None for c in cases): raise ValueError("missing operational annotations")
    if len(set(config["models"]))<3: raise ValueError("study requires three different models")
    if config["primary_model"] not in config["models"] or config["judge_model"] not in config["models"]:
        raise ValueError("primary/judge must belong to frozen panel")
    tags = request_json(config["base_url"],"/api/tags")["models"]
    installed = {m["name"]:m for m in tags}
    if any(name not in installed for name in config["models"]): raise ValueError("missing local models; no mock fallback")
    if any("cloud" in name for name in config["models"]): raise ValueError("cloud models are excluded")
    out = (path.parent/config["output"]).resolve()
    out.mkdir(parents=True,exist_ok=False)
    corpus = [c.model_dump(mode="json") for c in cases]
    engine = EngineConfig().model_dump(mode="json")
    manifest = {"study_id":config["study_id"],"timestamp":datetime.now(timezone.utc).isoformat(),
        "dataset_hash":digest(corpus),"config_hash":digest(config),"source_hash":source_hash(),
        "engine_config":engine,"engine_config_hash":digest(engine),"prismthinker_version":library_version,
        "git_commit":git("rev-parse","HEAD"),"runtime":request_json(config["base_url"],"/api/version"),
        "platform":platform.platform(),"python":platform.python_version(),
        "models":{m:installed[m] for m in config["models"]},"config":config,
        "prompt_hash":digest([PROMPT,JUDGE_PROMPT]),"case_count":len(cases),
        "group_count":len({c.metadata.group_id for c in cases}),
        "benchmark_type":"newly authored synthetic adversarial, frozen before evaluation; not externally reviewed",
        "heldout_definition":config.get("heldout_definition","No system output used for generation, selection or thresholds. All 180 cases are evaluation-only; no test-driven tuning."),
        "study_phase":config.get("study_phase","initial frozen run"),"input_preflight":preflight,
        "retry_policy":"No automatic retry. A started call without a completed record is a failed/unknown call on resume.",
        "shared_calls":"Single and panel sample zero are reused for self-consistency and majority/judge. Reported method costs include dependencies; physical calls are counted separately.",
        "representation":"Identical prose and typed rule inputs to all systems. Rule translation is authored; upstream extraction cost/generalization is not measured."}
    (out/"dataset.jsonl").write_text("".join(json.dumps(c,sort_keys=True)+"\n" for c in corpus),encoding="utf-8")
    write_json(out/"freeze.json",manifest)
    write_json(out/"freeze.sha256.json",{"sha256":digest(manifest)})
    return out


class Ledger:
    def __init__(self,path):
        self.path = path
        self.started, self.results = set(), {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                if event["event"] == "started": self.started.add(event["key"])
                else: self.results[event["key"]] = Result.model_validate_json(json.dumps(event["result"]))

    def append(self,event):
        with self.path.open("a",encoding="utf-8") as stream:
            stream.write(json.dumps(event,allow_nan=False)+"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def call(self,key,case_id,system,function):
        if key in self.results: return self.results[key]
        if key in self.started:
            result = Result(case_id=case_id,system=system,status=Status.ERROR,error="Interrupted call; outcome unknown; no retry permitted")
        else:
            self.append({"event":"started","key":key,"timestamp":datetime.now(timezone.utc).isoformat()})
            self.started.add(key)
            try: result = function()
            except Exception as exc:
                result = Result(case_id=case_id,system=system,status=Status.ERROR,error=f"{type(exc).__name__}: {exc}")
        self.append({"event":"completed","key":key,"result":result.model_dump(mode="json")})
        self.results[key] = result
        return result


def aggregate(case_id,name,samples):
    usage = Usage(model_ids=[m for r in samples for m in r.usage.model_ids],
        **{field:MajorityVote.total(samples,field) for field in ("calls","input_tokens","output_tokens","estimated_cost_usd")})
    raw = {"samples":[r.model_dump(mode="json") for r in samples]}
    latency = sum(r.latency_ms for r in samples)
    if not samples or any(r.status!=Status.OK for r in samples):
        return Result(case_id=case_id,system=name,status=Status.ERROR,error="Incomplete panel",usage=usage,raw=raw,latency_ms=latency)
    actions, verdicts = Counter(r.action for r in samples),Counter(r.verdict for r in samples)
    action,count = actions.most_common(1)[0]
    if count<=len(samples)/2: action=Action.ESCALATE
    verdict,votes = verdicts.most_common(1)[0]
    if votes<=len(samples)/2: verdict=Verdict.UNDETERMINED
    return Result(case_id=case_id,system=name,action=action,verdict=verdict,confidence=count/len(samples),
        conflict=len(verdicts)>1,hard_veto=sum(r.hard_veto is True for r in samples)>len(samples)/2,
        disagreement=1-votes/len(samples),confident_consensus=len(verdicts)==1 and min(r.confidence for r in samples)>=.9,
        reasoning="Strict count majority of operational directives; no majority escalates. Verdict is aggregated separately.",usage=usage,raw=raw,latency_ms=latency)


def run(out):
    out=Path(out).resolve()
    manifest=json.loads((out/"freeze.json").read_text())
    if digest(manifest)!=json.loads((out/"freeze.sha256.json").read_text())["sha256"]: raise ValueError("freeze manifest changed")
    if source_hash()!=manifest["source_hash"]: raise ValueError("code changed after freeze; refuse test-driven modifications")
    cases=load_cases(out/"dataset.jsonl")
    if digest([c.model_dump(mode="json") for c in cases])!=manifest["dataset_hash"]: raise ValueError("frozen corpus changed")
    cfg=manifest["config"]
    tags={m["name"]:m for m in request_json(cfg["base_url"],"/api/tags")["models"]}
    if any(tags.get(m,{}).get("digest")!=v["digest"] for m,v in manifest["models"].items()): raise ValueError("model digest changed")
    if request_json(cfg["base_url"],"/api/version")!=manifest["runtime"]: raise ValueError("runtime changed")
    # An OS file lock prevents concurrent runners; released automatically on crash.
    lock=(out/"run.lock").open("a+b")
    lock.seek(0); lock.write(b"1"); lock.flush(); lock.seek(0)
    if os.name=="nt":
        import msvcrt
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        ledger=Ledger(out/"calls.jsonl")
        for model in cfg["models"]:
            n=cfg["self_consistency_samples"] if model==cfg["primary_model"] else 1
            for i,case in enumerate(cases):
                for sample in range(n):
                    key=f"model:{model}:{case.case_id}:{sample}"
                    ledger.call(key,case.case_id,model,lambda c=case,s=sample,m=model:
                        evaluate(c.system_input(),m,cfg,cfg["seed"]+s))
                if (i+1)%10==0: print(f"{model}: {i+1}/{len(cases)}",flush=True)
        for i,case in enumerate(cases):
            panel=[ledger.results[f"model:{m}:{case.case_id}:0"] for m in cfg["models"]]
            settings={**cfg,"temperature":cfg["judge_temperature"]}
            ledger.call(f"judge:{case.case_id}",case.case_id,"judge",lambda c=case,p=panel:
                evaluate(c.system_input(),cfg["judge_model"],settings,cfg["seed"],p))
            if (i+1)%10==0: print(f"judge: {i+1}/{len(cases)}",flush=True)
        if source_hash()!=manifest["source_hash"]: raise ValueError("code changed during inference; do not mix implementations")
        engine=PrismThinkerAdapter()
        def prism(case):
            started=perf_counter()
            result=engine.evaluate(case.system_input())
            if cfg.get("semantic_conflict", False):
                flags=result.raw.get("conflict_signals", {})
                result.conflict=bool(flags.get("material_evidence_conflict") or flags.get("policy_authority_conflict"))
            result.latency_ms=(perf_counter()-started)*1000
            return result
        for case in cases:
            ledger.call(f"prism:{case.case_id}",case.case_id,"prismthinker",lambda c=case:prism(c))
        if cfg.get("include_eligibility_baseline", False):
            from validation.baselines.eligibility import EligibilityBaseline
            baseline = EligibilityBaseline()
            for case in cases:
                ledger.call(f"eligibility:{case.case_id}", case.case_id, baseline.name,
                            lambda c=case: baseline.evaluate(c.system_input()))
        rows=[]
        for case in cases:
            panel=[ledger.results[f"model:{m}:{case.case_id}:0"] for m in cfg["models"]]
            single=ledger.results[f"model:{cfg['primary_model']}:{case.case_id}:0"].model_copy(update={"system":"single_local"})
            sc=aggregate(case.case_id,"self_consistency",[ledger.results[f"model:{cfg['primary_model']}:{case.case_id}:{s}"] for s in range(cfg["self_consistency_samples"])])
            majority=aggregate(case.case_id,"majority_vote",panel)
            judge=ledger.results[f"judge:{case.case_id}"].model_copy(deep=True)
            deps=panel+[judge]
            judge.system="llm_judge"
            judge.latency_ms=sum(r.latency_ms for r in deps)
            judge.usage=Usage(model_ids=[m for r in deps for m in r.usage.model_ids],
                **{f:MajorityVote.total(deps,f) for f in ("calls","input_tokens","output_tokens","estimated_cost_usd")})
            results = [single,sc,majority,judge,ledger.results[f"prism:{case.case_id}"]]
            if cfg.get("include_eligibility_baseline", False):
                results.append(ledger.results[f"eligibility:{case.case_id}"])
            for result in results:
                rows.append({"case":case.model_dump(mode="json"),"result":result.model_dump(mode="json")})
        (out/"cases.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows),encoding="utf-8")
        write_json(out/"completion.json",{"state":"complete","timestamp":datetime.now(timezone.utc).isoformat(),
            "case_system_rows":len(rows),"physical_call_records":len(ledger.results),
            "physical_model_calls":sum(r.usage.calls or 0 for key,r in ledger.results.items() if not key.startswith("prism:")),
            "physical_model_calls_with_unknown_usage":sum(r.usage.calls is None for key,r in ledger.results.items() if not key.startswith("prism:"))})
        from validation.analysis.local_report import report
        report(out)
        if cfg.get("extended_analysis", False):
            from validation.analysis.fresh_report import report as extended_report
            extended_report(out)
        return out
    finally: lock.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["freeze","run","report"])
    parser.add_argument("path",type=Path)
    args=parser.parse_args()
    if args.command=="freeze": print(freeze(args.path))
    elif args.command=="run": print(run(args.path))
    else:
        from validation.analysis.local_report import report
        report(args.path)
