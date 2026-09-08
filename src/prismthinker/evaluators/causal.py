from __future__ import annotations

from collections import defaultdict, deque

from prismthinker.core.schemas import (
    AssumptionAtom,
    BackendKind,
    Citation,
    CitationKind,
    Claim,
    EvaluatorCapability,
    EvaluatorResult,
    Hypothesis,
    IndependenceClass,
    ReasoningContext,
    Verdict,
)
from prismthinker.evaluators.base import Evaluator
from prismthinker.reason_codes import REASON_MISSING_CAUSAL_GRAPH, REASON_UNBOUND_PATH

CAPABILITY = EvaluatorCapability(
    name="causal",
    backend=BackendKind.GRAPH,
    independence_class=IndependenceClass.CAUSAL_GRAPH,
    may_hard_veto=False,
)


def _reachable(
    edges: list[tuple[str, str, int | None]],
    start: str,
    goal: str,
    cut_incoming: set[str],
) -> tuple[bool, list[list[int | None]]]:
    adj: dict[str, list[tuple[str, int | None]]] = defaultdict(list)
    for src, dst, signed in edges:
        if dst in cut_incoming:
            continue
        adj[src].append((dst, signed))

    sign_paths: list[list[int | None]] = []
    queue: deque[tuple[str, list[int | None], set[str]]] = deque([(start, [], set())])
    found = False
    visited_states = 0
    while queue:
        visited_states += 1
        if visited_states > 10000:
            raise ValueError("causal traversal budget exceeded")
        node, signs, seen = queue.popleft()
        if node == goal:
            found = True
            sign_paths.append(signs)
            continue
        if node in seen:
            continue
        nxt = seen | {node}
        for dest, signed in adj.get(node, []):
            extra = list(signs)
            extra.append(signed)
            queue.append((dest, extra, nxt))
            if len(queue) > 10000:
                raise ValueError("causal traversal budget exceeded")
    return found, sign_paths


class CausalEvaluator(Evaluator):
    capability = CAPABILITY

    def evaluate(self, context: ReasoningContext, hypothesis: Hypothesis) -> EvaluatorResult:
        graph = context.causal_graph
        if graph is None:
            return EvaluatorResult(
                evaluator="causal",
                verdict=Verdict.UNDETERMINED,
                confidence=0.0,
                unresolved_questions=["causal_graph is required"],
                reason_codes=[REASON_MISSING_CAUSAL_GRAPH],
                backend=BackendKind.GRAPH,
            )

        payload = hypothesis.action.payload if hypothesis.action else {}
        treatment = payload.get("treatment")
        outcome = payload.get("outcome")
        inferred = False
        if not treatment and hypothesis.action is not None:
            for key in hypothesis.action.payload:
                if key not in {"treatment", "outcome", "do", "effect_sign"}:
                    treatment = key
                    inferred = True
                    break
        if not outcome and context.objective is not None and context.objective.terms:
            outcome = context.objective.terms[0].fact_key
            inferred = True

        if not treatment or not outcome:
            return EvaluatorResult(
                evaluator="causal",
                verdict=Verdict.UNDETERMINED,
                confidence=0.0,
                unresolved_questions=["missing treatment/outcome binding"],
                reason_codes=[REASON_UNBOUND_PATH],
                backend=BackendKind.GRAPH,
            )

        treatment = str(treatment)
        outcome = str(outcome)
        edges = [(e.source, e.target, e.signed) for e in graph.edges]
        do_nodes: set[str] = set()
        if "do" in payload:
            raw = payload["do"]
            if isinstance(raw, list):
                do_nodes.update(str(x) for x in raw)
            else:
                do_nodes.add(str(raw))
        for key, fact in context.structured_facts.items():
            if key.startswith("do."):
                do_nodes.add(key[3:])

        try:
            reachable, sign_paths = _reachable(edges, treatment, outcome, do_nodes)
        except ValueError as exc:
            return EvaluatorResult(evaluator="causal", verdict=Verdict.UNDETERMINED,
                confidence=0.0, unresolved_questions=[str(exc)],
                reason_codes=[REASON_UNBOUND_PATH], backend=BackendKind.GRAPH)
        premises = [e.edge_id for e in graph.edges]
        citations = [
            Citation(kind=CitationKind.GRAPH_EDGE, ref=e.edge_id) for e in graph.edges[:8]
        ] or [Citation(kind=CitationKind.HYPOTHESIS, ref=hypothesis.id)]

        effect_sign = payload.get("effect_sign", 1)
        if type(effect_sign) is not int or effect_sign not in (-1, 1):
            return EvaluatorResult(evaluator="causal", verdict=Verdict.UNDETERMINED,
                confidence=0.0, unresolved_questions=["effect_sign must be -1 or 1"],
                reason_codes=[REASON_UNBOUND_PATH], backend=BackendKind.GRAPH)
        assumptions = [
            AssumptionAtom(
                id="causal-faithful",
                predicate="causal_graph.faithful",
                polarity=True,
            ),
            AssumptionAtom(
                id="causal-path",
                predicate=f"path({treatment}->{outcome})",
                polarity=reachable,
            ),
        ]
        if not reachable:
            return EvaluatorResult(
                evaluator="causal",
                verdict=Verdict.UNDETERMINED,
                unresolved_questions=["missing directed causal path"],
                confidence=0.5 if inferred else 0.85,
                claims=[
                    Claim(
                        id="causal-path",
                        evaluator="causal",
                        statement=f"no path from {treatment} to {outcome}",
                        polarity=-1.0,
                        confidence=0.85,
                        citations=citations,
                        hypothesis_id=hypothesis.id,
                    )
                ],
                premise_ids=premises,
                assumptions=assumptions,
                backend=BackendKind.GRAPH,
            )

        # Universal signed-path contract: a known counterexample defeats the
        # claim even when other paths contain unknown signs. A zero edge fixes
        # the product at zero even if another edge is unknown.
        products = [0 if 0 in p else _product(p) for p in sign_paths if p and (0 in p or None not in p)]
        if any(product != effect_sign for product in products):
            return EvaluatorResult(
                evaluator="causal",
                verdict=Verdict.REJECT,
                confidence=0.5 if inferred else 0.85,
                claims=[
                    Claim(
                        id="causal-sign",
                        evaluator="causal",
                        statement="a directed path contradicts the claimed effect sign",
                        polarity=-1.0,
                        confidence=0.85,
                        citations=citations,
                        hypothesis_id=hypothesis.id,
                    )
                ],
                premise_ids=premises,
                assumptions=assumptions,
                backend=BackendKind.GRAPH,
            )

        if any(not p or (None in p and 0 not in p) for p in sign_paths):
            return EvaluatorResult(evaluator="causal", verdict=Verdict.UNDETERMINED,
                confidence=0.0, unresolved_questions=["missing causal path sign"],
                reason_codes=[REASON_UNBOUND_PATH], backend=BackendKind.GRAPH)

        return EvaluatorResult(
            evaluator="causal",
            verdict=Verdict.APPROVE,
            confidence=0.5 if inferred else 0.85,
            claims=[
                Claim(
                    id="causal-ok",
                    evaluator="causal",
                    statement=f"{treatment} reaches {outcome}",
                    polarity=1.0,
                    confidence=0.85,
                    citations=citations,
                    hypothesis_id=hypothesis.id,
                )
            ],
            premise_ids=premises,
            assumptions=assumptions,
            backend=BackendKind.GRAPH,
        )


def _product(signs: list[int]) -> int:
    acc = 1
    for s in signs:
        acc *= s
    return acc
