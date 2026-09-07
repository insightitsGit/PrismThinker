from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from prismthinker import PresentationContext, PrismThinker
from prismthinker.adapters.chorusgraph import (
    ChorusGraphOrchestrateRequest,
    to_chorusgraph,
)
from prismthinker.adapters.documents import RetrieveRequest, from_documents
from prismthinker.config import EngineConfig
from prismthinker.core.schemas import DecisionGraph

from bench.corpus import corpus_documents
from bench.neighbors import LocalChorusGraph, LocalRetriever
from bench.scenarios import Scenario, all_scenarios

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "bench" / "out"


def bench_config(**overrides: Any) -> EngineConfig:
    payload = {"isolate_heads": False, **overrides}
    return EngineConfig(**payload)


def prior_grid() -> list[EngineConfig]:
    configs = [bench_config()]
    seen = {configs[0].model_dump_json()}
    for tau in (0.30, 0.40, 0.50):
        for qualified in (0.10, 0.20, 0.30):
            for insufficient in (0.50, 0.60, 0.70):
                cfg = bench_config(
                    tau_base=tau,
                    qualified_tau=qualified,
                    u_insufficient=insufficient,
                )
                key = cfg.model_dump_json()
                if key not in seen:
                    configs.append(cfg)
                    seen.add(key)
    return configs


def score_case(
    scenario: Scenario,
    graph: DecisionGraph,
    directive: str,
    executed_tools: list[str],
    retrieved_ids: list[str] | None,
) -> dict[str, bool]:
    gold = scenario.gold
    checks: dict[str, bool] = {}
    if gold.disposition:
        checks["disposition"] = graph.disposition.value == gold.disposition
    if gold.directive:
        checks["directive"] = directive == gold.directive
    if gold.disposition in {"conflict", "insufficient_evidence"}:
        checks["verdict_null"] = graph.recommended_verdict is None
    elif gold.verdict:
        actual = None if graph.recommended_verdict is None else graph.recommended_verdict.value
        checks["verdict"] = actual == gold.verdict
    if gold.regime:
        checks["regime"] = graph.regime.value == gold.regime
    if gold.evidence_types:
        types = {item.conflict_type.value for item in graph.evidence_conflicts}
        checks["evidence"] = set(gold.evidence_types).issubset(types)
    if gold.resolving_param:
        checks["counterfactual"] = any(
            probe.parameter_changed == gold.resolving_param and probe.resolving
            for probe in graph.counterfactuals
        )
    if gold.executed_tools is not None:
        checks["tools"] = tuple(executed_tools) == gold.executed_tools
    if scenario.expected_doc_ids and retrieved_ids is not None:
        checks["retrieval"] = set(scenario.expected_doc_ids).issubset(set(retrieved_ids))
    return checks


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def run_scenario(
    scenario: Scenario,
    thinker: PrismThinker,
    retriever,
    orchestrator,
    *,
    save_dir: Path | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    retrieved_ids: list[str] | None = None
    retrieve_ms = 0.0
    seed = scenario.seed.model_copy(update={"query": scenario.query}, deep=True)
    if scenario.retrieve:
        request = RetrieveRequest(query=scenario.query, top_k=scenario.top_k)
        response = retriever.retrieve(request)
        retrieve_ms = response.took_ms
        retrieved_ids = [doc.id for doc in response.documents]
        context = from_documents(
            scenario.query,
            response.documents,
            hypothesis=seed.hypothesis,
            extra=seed,
        )
        if save_dir is not None:
            _write_json(save_dir / "retrieve_request.json", request.model_dump(mode="json"))
            _write_json(save_dir / "retrieve_response.json", response.model_dump(mode="json"))
    else:
        context = seed

    graph = thinker.evaluate(context)
    envelope = to_chorusgraph(graph, allowed_tools=list(scenario.tools))
    orch_req = ChorusGraphOrchestrateRequest(
        envelope=envelope,
        requested_tools=list(scenario.tools),
        presentation=PresentationContext(user_id=scenario.presentation_user)
        if scenario.presentation_user
        else None,
    )
    orch = orchestrator.orchestrate(orch_req)
    if save_dir is not None:
        _write_json(
            save_dir / "orchestrate_request.json",
            {
                "requested_tools": orch_req.requested_tools,
                "presentation": None
                if orch_req.presentation is None
                else orch_req.presentation.model_dump(mode="json"),
                "directive": envelope.directive.value,
                "allowed_tools": envelope.allowed_tools,
                "gather_fact_keys": envelope.gather_fact_keys,
                "run_id": graph.run_id,
            },
        )
        _write_json(save_dir / "orchestrate_response.json", orch.model_dump(mode="json"))
        _write_json(
            save_dir / "decision_summary.json",
            {
                "disposition": graph.disposition.value,
                "directive": envelope.directive.value,
                "verdict": None if graph.recommended_verdict is None else graph.recommended_verdict.value,
                "regime": graph.regime.value,
                "delta": graph.contradiction_score,
                "uncertainty": graph.uncertainty_score,
                "review_required": graph.review_required,
                "evaluators": {name: res.verdict.value for name, res in graph.evaluators.items()},
                "evidence_conflicts": [c.conflict_type.value for c in graph.evidence_conflicts],
                "timings_ms": graph.timings_ms,
            },
        )

    checks = score_case(
        scenario,
        graph,
        envelope.directive.value,
        list(orch.executed_tools),
        retrieved_ids,
    )
    return {
        "id": scenario.id,
        "families": list(scenario.gold.families),
        "contract": scenario.gold.contract,
        "checks": checks,
        "passed": all(checks.values()) if checks else True,
        "contract_passed": all(
            value
            for key, value in checks.items()
            if key in {"disposition", "directive", "verdict", "verdict_null", "tools"}
        )
        if scenario.gold.contract
        else True,
        "disposition": graph.disposition.value,
        "directive": envelope.directive.value,
        "verdict": None if graph.recommended_verdict is None else graph.recommended_verdict.value,
        "regime": graph.regime.value,
        "delta": graph.contradiction_score,
        "uncertainty": graph.uncertainty_score,
        "review_required": graph.review_required,
        "evaluators": {name: res.verdict.value for name, res in graph.evaluators.items()},
        "evidence_conflicts": [c.conflict_type.value for c in graph.evidence_conflicts],
        "executed_tools": list(orch.executed_tools),
        "blocked_reason": orch.blocked_reason,
        "retrieved_ids": retrieved_ids,
        "retrieve_ms": retrieve_ms,
        "eval_ms": graph.timings_ms.get("total", 0.0),
        "wall_ms": (time.perf_counter() - started) * 1000.0,
        "fast_path": graph.fast_path is not None,
    }


def _connect_docker(vector_url: str, chorus_url: str, timeout_s: float = 90.0):
    from prismthinker.adapters.clients import ChorusGraphClient, RetrieverClient

    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        try:
            vector = RetrieverClient(vector_url)
            chorus = ChorusGraphClient(chorus_url)
            vector.health()
            chorus.health()
            return vector, chorus
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            time.sleep(1.5)
    raise RuntimeError(f"docker neighbors not healthy: {last}")


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labeled = [row for row in rows if row["checks"]]
    contract = [row for row in rows if row["contract"]]
    walls = [row["wall_ms"] for row in rows]
    evals = [row["eval_ms"] for row in rows]
    retrieve = [row["retrieve_ms"] for row in rows if row["retrieve_ms"]]
    family_hits: dict[str, list[bool]] = defaultdict(list)
    for row in rows:
        ok = row["passed"]
        for family in row["families"]:
            family_hits[family].append(ok)
    check_hits: dict[str, list[bool]] = defaultdict(list)
    for row in rows:
        for name, ok in row["checks"].items():
            check_hits[name].append(ok)
    return {
        "n": len(rows),
        "labeled": len(labeled),
        "pass_rate": (sum(1 for row in labeled if row["passed"]) / len(labeled)) if labeled else 1.0,
        "contract_rate": (sum(1 for row in contract if row["contract_passed"]) / len(contract))
        if contract
        else 1.0,
        "disposition_hist": dict(Counter(row["disposition"] for row in rows)),
        "directive_hist": dict(Counter(row["directive"] for row in rows)),
        "regime_hist": dict(Counter(row["regime"] for row in rows)),
        "family_pass_rate": {
            name: sum(hits) / len(hits) for name, hits in sorted(family_hits.items())
        },
        "check_pass_rate": {name: sum(hits) / len(hits) for name, hits in sorted(check_hits.items())},
        "latency": {
            "eval_p50_ms": statistics.median(evals) if evals else 0.0,
            "eval_max_ms": max(evals) if evals else 0.0,
            "wall_p50_ms": statistics.median(walls) if walls else 0.0,
            "wall_max_ms": max(walls) if walls else 0.0,
            "retrieve_p50_ms": statistics.median(retrieve) if retrieve else 0.0,
        },
        "failures": [
            {
                "id": row["id"],
                "checks": {k: v for k, v in row["checks"].items() if not v},
                "disposition": row["disposition"],
                "directive": row["directive"],
                "verdict": row["verdict"],
            }
            for row in rows
            if not row["passed"]
        ],
    }


def run_suite(
    configs: Iterable[EngineConfig],
    retriever,
    orchestrator,
    out_dir: Path,
    *,
    save_payloads: bool,
) -> dict[str, Any]:
    scenarios = all_scenarios()
    reports = []
    default_key = bench_config().model_dump_json()
    for index, config in enumerate(configs):
        thinker = PrismThinker(config)
        is_default = config.model_dump_json() == default_key
        rows = []
        for scenario in scenarios:
            save = out_dir / "payloads" / scenario.id if save_payloads and is_default else None
            rows.append(run_scenario(scenario, thinker, retriever, orchestrator, save_dir=save))
        prior = {
            "tau_base": config.tau_base,
            "qualified_tau": config.qualified_tau,
            "u_insufficient": config.u_insufficient,
            "default": is_default,
        }
        reports.append({"prior": prior, "summary": _summarize(rows), "rows": rows})
        print(
            f"[{index + 1}] tau={config.tau_base:.2f} q={config.qualified_tau:.2f} "
            f"u={config.u_insufficient:.2f} pass={reports[-1]['summary']['pass_rate']:.3f} "
            f"contract={reports[-1]['summary']['contract_rate']:.3f}"
        )
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_scenarios": len(scenarios),
        "n_priors": len(reports),
        "reports": reports,
    }


def _best_prior(bundle: dict[str, Any]) -> dict[str, Any]:
    ranked = sorted(
        bundle["reports"],
        key=lambda item: (item["summary"]["contract_rate"], item["summary"]["pass_rate"]),
        reverse=True,
    )
    return {"prior": ranked[0]["prior"], "summary": ranked[0]["summary"]}


def write_markdown(bundle: dict[str, Any], path: Path) -> None:
    default = next(item for item in bundle["reports"] if item["prior"]["default"])
    best = _best_prior(bundle)
    lines = [
        "# PrismThinker prior benchmark",
        "",
        f"Scenarios: {bundle['n_scenarios']}. Prior grid: {bundle['n_priors']}.",
        "",
        "## Default priors (`tau=0.40`, `qualified=0.20`, `u=0.60`)",
        "",
        f"- Labeled pass rate: {default['summary']['pass_rate']:.3f}",
        f"- Contract hold rate: {default['summary']['contract_rate']:.3f}",
        f"- Eval p50: {default['summary']['latency']['eval_p50_ms']:.1f} ms",
        "",
        "### Disposition counts",
        "",
    ]
    for key, value in default["summary"]["disposition_hist"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "### Family pass rate", ""])
    for key, value in default["summary"]["family_pass_rate"].items():
        lines.append(f"- {key}: {value:.3f}")
    lines.extend(["", "### Failures under default priors", ""])
    if not default["summary"]["failures"]:
        lines.append("- none")
    for item in default["summary"]["failures"]:
        lines.append(
            f"- `{item['id']}` got {item['disposition']}/{item['directive']} missed {item['checks']}"
        )
    lines.extend(
        [
            "",
            "## Best prior on this grid",
            "",
            f"- tau_base={best['prior']['tau_base']} qualified_tau={best['prior']['qualified_tau']} "
            f"u_insufficient={best['prior']['u_insufficient']}",
            f"- pass={best['summary']['pass_rate']:.3f} contract={best['summary']['contract_rate']:.3f}",
            "",
            "These are measurements of engineering priors, not a claim that the winner is calibrated.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wire retrieve/orchestrate payloads and benchmark priors")
    parser.add_argument("--backend", choices=("docker", "local"), default="docker")
    parser.add_argument("--vector-url", default="http://127.0.0.1:8081")
    parser.add_argument("--chorus-url", default="http://127.0.0.1:8082")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-sweep", action="store_true")
    args = parser.parse_args(argv)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = corpus_documents()

    if args.backend == "docker":
        retriever, orchestrator = _connect_docker(args.vector_url, args.chorus_url)
        indexed = retriever.index(docs)
        print(f"indexed {indexed.indexed} documents via {indexed.backend}")
    else:
        retriever = LocalRetriever()
        retriever.index(docs)
        orchestrator = LocalChorusGraph()
        print(f"indexed {len(docs)} documents via memory store")

    configs = [bench_config()] if args.no_sweep else prior_grid()
    print(f"running {len(all_scenarios())} scenarios × {len(configs)} prior configs")
    bundle = run_suite(configs, retriever, orchestrator, out_dir, save_payloads=True)
    bundle["backend"] = args.backend
    bundle["best_prior"] = _best_prior(bundle)
    _write_json(out_dir / "report.json", bundle)
    write_markdown(bundle, out_dir / "report.md")
    print(f"wrote {out_dir / 'report.json'}")
    print(
        f"default pass={next(r['summary']['pass_rate'] for r in bundle['reports'] if r['prior']['default']):.3f} "
        f"best pass={bundle['best_prior']['summary']['pass_rate']:.3f}"
    )
    if args.backend == "docker":
        retriever.close()
        orchestrator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
