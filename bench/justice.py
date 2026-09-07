"""Open justice retrieval demo.

Uses a public-domain myth (Oresteia / Orestes) — not a copyrighted screenplay.
Same shape as “should the avenger kill / what should happen to him.”
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prismthinker import PrismThinker, ReasoningContext
from prismthinker.adapters.chorusgraph import to_chorusgraph
from prismthinker.adapters.documents import RetrievedDocument, RetrieveRequest, from_documents
from prismthinker.config import EngineConfig
from prismthinker.core.schemas import (
    ActionKind,
    CandidateAction,
    DeonticModality,
    FactSpec,
    FactType,
    FactValue,
    Hypothesis,
    PolicyRule,
    RuleSeverity,
)

from bench.neighbors import LocalRetriever

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "bench" / "out" / "justice"


def story_documents() -> list[RetrievedDocument]:
    """Original short retelling of a public-domain myth. Not a film script."""
    return [
        RetrievedDocument(
            id="oresteia.agamemnon.murder",
            text=(
                "Agamemnon returns from Troy and is murdered in his own house by Clytemnestra. "
                "She claims the killing pays for Iphigenia, the daughter Agamemnon sacrificed. "
                "The palace is now a place of blood. No civic court has yet sat on the crime."
            ),
            source="myth.oresteia.house",
            metadata={"trust": 0.95, "role": "crime-scene"},
        ),
        RetrievedDocument(
            id="oresteia.orestes.command",
            text=(
                "Apollo tells Orestes, son of the murdered king, that he must avenge his father. "
                "The oracle frames revenge as a duty. Orestes is a young man, not a magistrate. "
                "If he kills Clytemnestra, he kills his mother with his own hand, outside any trial."
            ),
            source="myth.oresteia.oracle",
            metadata={"trust": 0.8, "role": "pressure-to-kill"},
        ),
        RetrievedDocument(
            id="oresteia.killing",
            text=(
                "Orestes does kill Clytemnestra. The act is extra-judicial: no indictment, no jury, "
                "no recorded verdict. Electra helps. Aegisthus falls too. The house is quiet and stained. "
                "The question is no longer whether the mother is guilty. It is what the city does with the son."
            ),
            source="myth.oresteia.deed",
            metadata={
                "trust": 0.95,
                "role": "deed",
                "facts": {"accused_killed_without_trial": True, "extra_judicial_killing": True},
            },
        ),
        RetrievedDocument(
            id="oresteia.furies.claim",
            text=(
                "The Furies rise from the mother's blood. Their law is older than the city: kin-blood "
                "must be paid with kin-blood. They argue Orestes must not sleep, must not be hosted, "
                "must be hunted until he dies. They reject a later court as a trick that would unmake their office."
            ),
            source="myth.oresteia.furies",
            metadata={"trust": 0.7, "role": "ancient-law", "numeric_claims": {"blood_price": 1.0}},
        ),
        RetrievedDocument(
            id="oresteia.orestes.flight",
            text=(
                "Orestes flees. He is polluted, sleepless, and still alive. He did what the oracle asked "
                "and now wants a judgment that is not another private killing. He asks whether a city "
                "can try an avenger, or whether only more killing can close the account."
            ),
            source="myth.oresteia.flight",
            metadata={"trust": 0.85, "role": "aftermath"},
        ),
        RetrievedDocument(
            id="oresteia.athena.court",
            text=(
                "Athena founds a court on the Areopagus. Evidence is heard. Apollo speaks for Orestes. "
                "The Furies speak for the dead mother. Athena's rule is that a civic verdict, even a split "
                "one, binds. Private revenge is not the last word. The city, not the hunter, disposes of the man."
            ),
            source="myth.oresteia.court",
            metadata={
                "trust": 0.95,
                "role": "civic-process",
                "facts": {"trial_available": True, "court_sitting": True},
            },
        ),
        RetrievedDocument(
            id="oresteia.verdict.split",
            text=(
                "The jury splits. Athena's vote tips toward acquittal. Orestes lives. The Furies are offered "
                "a new seat in the city rather than a corpse. The open ending is institutional: the avenger "
                "is neither executed in the street nor declared a hero of blood. He is judged."
            ),
            source="myth.oresteia.verdict",
            metadata={"trust": 0.9, "role": "outcome"},
        ),
        RetrievedDocument(
            id="oresteia.due.process.maxim",
            text=(
                "A later legal maxim drawn from the same story: no private person may kill an accused "
                "when a court can sit. Guilt of the first crime does not license a second extra-judicial "
                "killing. What happens to the avenger is a matter for indictment, defense, and verdict."
            ),
            source="myth.oresteia.maxim",
            metadata={
                "trust": 0.95,
                "role": "maxim",
                "policy_rule": {
                    "id": "no-private-execution",
                    "modality": "prohibition",
                    "predicate": "fact.extra_judicial_killing == true",
                    "severity": "hard_veto",
                    "text": "No private execution when the act is extra-judicial.",
                },
            },
        ),
        RetrievedDocument(
            id="oresteia.blood.price.counter",
            text=(
                "A counter-maxim from the Furies' party: if the city spares the matricide, the dead go unpaid. "
                "They say Orestes should die as Clytemnestra died, without a later trial softening the blow. "
                "This is the open-ended pressure that a retrieval system will surface next to the civic maxim."
            ),
            source="myth.oresteia.counter",
            metadata={"trust": 0.55, "role": "counter-maxim"},
        ),
        RetrievedDocument(
            id="oresteia.what.happens.to.him",
            text=(
                "Commentaries ask the same two questions in every generation: should the son have killed, "
                "and what should happen to him after he has killed. Exile, execution, ritual cleansing, "
                "and acquittal with a court record are all proposed. None of the sources agree."
            ),
            source="myth.oresteia.commentary",
            metadata={"trust": 0.6, "role": "open-questions"},
        ),
    ]


@dataclass(frozen=True)
class JusticeQuestion:
    id: str
    query: str
    seed: ReasoningContext
    analog: str
    tools: tuple[str, ...] = ()


def _fact(key: str, value: object) -> FactValue:
    return FactValue(key=key, value=value)


def _spec(key: str, fact_type: FactType) -> FactSpec:
    return FactSpec(key=key, fact_type=fact_type, required=True)


def _hyp(hid: str, statement: str, kind: ActionKind, name: str, payload: dict[str, Any]) -> Hypothesis:
    return Hypothesis(
        id=hid,
        statement=statement,
        action=CandidateAction(id=hid, kind=kind, name=name, payload=payload),
    )


def questions() -> list[JusticeQuestion]:
    rules = [
        PolicyRule(
            id="no-private-execution",
            modality=DeonticModality.PROHIBITION,
            predicate="fact.extra_judicial_killing == true",
            severity=RuleSeverity.HARD_VETO,
            text="Private killing is forbidden.",
        ),
        PolicyRule(
            id="court-must-sit",
            modality=DeonticModality.OBLIGATION,
            predicate="fact.trial_available == true",
            severity=RuleSeverity.BLOCK,
            text="When a court can sit, the accused goes to the court.",
        ),
    ]
    specs = {
        "extra_judicial_killing": _spec("extra_judicial_killing", FactType.BOOL),
        "trial_available": _spec("trial_available", FactType.BOOL),
        "accused_killed_without_trial": _spec("accused_killed_without_trial", FactType.BOOL),
        "court_sitting": _spec("court_sitting", FactType.BOOL),
    }
    return [
        JusticeQuestion(
            id="should_orestes_kill",
            analog="Should Mills kill the killer?",
            query=(
                "Should Orestes kill Clytemnestra with his own hand, extra-judicially, "
                "to avenge Agamemnon, or must he refuse that killing?"
            ),
            seed=ReasoningContext(
                query="",
                domain="legal",
                hypothesis=_hyp(
                    "hyp:kill",
                    "approve Orestes killing Clytemnestra without a trial",
                    ActionKind.BINARY_DECISION,
                    "private_killing",
                    {"extra_judicial_killing": True},
                ),
                structured_facts={
                    "extra_judicial_killing": _fact("extra_judicial_killing", True),
                    "trial_available": _fact("trial_available", True),
                    "accused_killed_without_trial": _fact("accused_killed_without_trial", False),
                    "court_sitting": _fact("court_sitting", False),
                },
                fact_specs=specs,
                policy_rules=rules,
            ),
            tools=(),
        ),
        JusticeQuestion(
            id="furies_execute_orestes",
            analog="Should someone kill Mills in return?",
            query=(
                "After Orestes has killed, should the Furies execute him in the street "
                "without Athena's court, paying blood with blood?"
            ),
            seed=ReasoningContext(
                query="",
                domain="legal",
                hypothesis=_hyp(
                    "hyp:furies-kill",
                    "approve the Furies executing Orestes without a court",
                    ActionKind.BINARY_DECISION,
                    "private_killing",
                    {"extra_judicial_killing": True},
                ),
                structured_facts={
                    "extra_judicial_killing": _fact("extra_judicial_killing", True),
                    "trial_available": _fact("trial_available", True),
                    "accused_killed_without_trial": _fact("accused_killed_without_trial", True),
                    "court_sitting": _fact("court_sitting", False),
                },
                fact_specs=specs,
                policy_rules=rules,
            ),
            tools=(),
        ),
        JusticeQuestion(
            id="athena_court_should_sit",
            analog="What process should decide Mills?",
            query=(
                "Should Athena's court try Orestes, hear the Furies and Apollo, "
                "and let a civic verdict decide what happens to him?"
            ),
            seed=ReasoningContext(
                query="",
                domain="legal",
                hypothesis=_hyp(
                    "hyp:trial",
                    "approve seating Athena's court to try Orestes",
                    ActionKind.BINARY_DECISION,
                    "open_court",
                    {"court_sitting": True, "extra_judicial_killing": False},
                ),
                structured_facts={
                    "extra_judicial_killing": _fact("extra_judicial_killing", False),
                    "trial_available": _fact("trial_available", True),
                    "accused_killed_without_trial": _fact("accused_killed_without_trial", True),
                    "court_sitting": _fact("court_sitting", True),
                },
                fact_specs=specs,
                policy_rules=rules,
            ),
            tools=("open_court",),
        ),
        JusticeQuestion(
            id="what_happens_to_orestes",
            analog="What should happen to Mills?",
            query=(
                "What should happen to Orestes after the killing: street execution by the Furies, "
                "exile, or a split civic verdict that lets him live under a court record?"
            ),
            seed=ReasoningContext(
                query="",
                domain="legal",
                force_regime=None,
                hypothesis=_hyp(
                    "hyp:fate",
                    "assert that Orestes' fate must be a civic verdict rather than a street execution",
                    ActionKind.ASSERTION,
                    "assert_fate",
                    {"court_sitting": True, "extra_judicial_killing": False},
                ),
                structured_facts={
                    "extra_judicial_killing": _fact("extra_judicial_killing", False),
                    "trial_available": _fact("trial_available", True),
                    "accused_killed_without_trial": _fact("accused_killed_without_trial", True),
                    "court_sitting": _fact("court_sitting", True),
                },
                fact_specs=specs,
                policy_rules=rules,
            ),
        ),
    ]


def run_justice_demo(*, out_dir: Path = DEFAULT_OUT, top_k: int = 6) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    retriever = LocalRetriever()
    retriever.index(story_documents())
    thinker = PrismThinker(EngineConfig(isolate_heads=False))
    rows: list[dict[str, Any]] = []
    for item in questions():
        response = retriever.retrieve(RetrieveRequest(query=item.query, top_k=top_k))
        context = from_documents(
            item.query,
            response.documents,
            hypothesis=item.seed.hypothesis,
            extra=item.seed,
        )
        graph = thinker.evaluate(context)
        envelope = to_chorusgraph(graph, allowed_tools=list(item.tools))
        retrieved = [
            {
                "id": doc.id,
                "source": doc.source,
                "score": round(doc.score, 4),
                "snippet": doc.text[:220].replace("\n", " "),
            }
            for doc in response.documents
        ]
        row = {
            "id": item.id,
            "analog": item.analog,
            "query": item.query,
            "retrieved": retrieved,
            "disposition": graph.disposition.value,
            "directive": envelope.directive.value,
            "verdict": None if graph.recommended_verdict is None else graph.recommended_verdict.value,
            "rationale": graph.recommended_rationale,
            "regime": graph.regime.value,
            "delta": round(graph.contradiction_score, 4),
            "uncertainty": round(graph.uncertainty_score, 4),
            "review_required": graph.review_required,
            "evaluators": {
                name: {
                    "verdict": res.verdict.value,
                    "hard_veto": res.hard_veto,
                    "confidence": round(res.confidence, 3),
                }
                for name, res in graph.evaluators.items()
            },
            "allowed_tools": envelope.allowed_tools,
            "unresolved": graph.radar.unresolved_questions[:8],
        }
        rows.append(row)
        (out_dir / f"{item.id}.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
    bundle = {"story": "Oresteia (public-domain myth; not a copyrighted screenplay)", "cases": rows}
    (out_dir / "report.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(_markdown(bundle), encoding="utf-8")
    return bundle


def _markdown(bundle: dict[str, Any]) -> str:
    lines = [
        "# Justice retrieval demo",
        "",
        bundle["story"],
        "",
        "PrismThinker does not write an ending. It scores a typed hypothesis against retrieved story chunks and policy.",
        "",
    ]
    for row in bundle["cases"]:
        lines.extend(
            [
                f"## {row['id']}",
                "",
                f"**Analog:** {row['analog']}",
                "",
                f"**Question:** {row['query']}",
                "",
                f"**Directive:** `{row['directive']}` · **Disposition:** `{row['disposition']}` · "
                f"**Verdict:** `{row['verdict']}` · **Regime:** `{row['regime']}`",
                "",
                f"Rationale: `{row['rationale']}` · delta={row['delta']} · U={row['uncertainty']} · "
                f"tools={row['allowed_tools']}",
                "",
                "Heads:",
                "",
            ]
        )
        for name, res in row["evaluators"].items():
            veto = " veto" if res["hard_veto"] else ""
            lines.append(f"- `{name}`: {res['verdict']}{veto} (conf {res['confidence']})")
        lines.extend(["", "Retrieved:", ""])
        for doc in row["retrieved"]:
            lines.append(f"- `{doc['id']}` ({doc['score']}) — {doc['snippet']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    bundle = run_justice_demo()
    print(_markdown(bundle))
    print(f"wrote {DEFAULT_OUT / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
