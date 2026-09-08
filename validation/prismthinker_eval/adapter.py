from prismthinker import PrismThinker, ReasoningDisposition
from prismthinker.adapters.chorusgraph import to_chorusgraph
from validation.schemas.case import Verdict
from validation.schemas.result import Result, Action, Usage


class PrismThinkerAdapter:
    name = "prismthinker"

    def __init__(self, consensus_confidence=0.8):
        self.engine = PrismThinker()
        self.consensus_confidence = consensus_confidence

    def evaluate(self, case):
        graph = self.engine.evaluate(case.reasoning_context())
        verdict = Verdict(graph.recommended_verdict.value.upper()) if graph.recommended_verdict else Verdict.UNDETERMINED
        return Result(case_id=case.case_id, system=self.name, verdict=verdict,
                      action=Action(to_chorusgraph(graph).directive.value.upper()),
                      confidence=graph.confidence, reasoning=graph.recommended_rationale,
                      conflict=bool(graph.conflict_signals.material_evidence_conflict
                                    or graph.conflict_signals.policy_authority_conflict
                                    or graph.disposition == ReasoningDisposition.CONFLICT
                                    or graph.critical_conflicts or graph.evidence_conflicts
                                    or graph.conflicting_assumptions),
                      hard_veto=graph.disposition == ReasoningDisposition.HARD_VETO,
                      confident_consensus=(graph.disposition in {
                          ReasoningDisposition.CONSENSUS, ReasoningDisposition.QUALIFIED_CONSENSUS}
                          and graph.confidence >= self.consensus_confidence),
                      delta=graph.contradiction_score, uncertainty=graph.uncertainty_score,
                      usage=Usage(calls=0, input_tokens=0, output_tokens=0, estimated_cost_usd=0.0),
                      raw=graph.model_dump(mode="json"))
