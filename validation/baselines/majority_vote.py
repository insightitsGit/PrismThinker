from collections import Counter
from validation.baselines.single_model import SingleModel, call_provider
from validation.schemas.case import Verdict
from validation.schemas.result import Result, Usage, Status
from validation.prismthinker_eval.action_policy import action_for


class MajorityVote(SingleModel):
    name = "majority_vote_mock"

    def __init__(self, providers, consensus_confidence=0.8):
        self.providers = providers
        self.consensus_confidence = consensus_confidence

    def evaluate(self, case):
        samples = [call_provider(p, case) for p in self.providers]
        if not samples:
            raise ValueError("majority vote requires providers")
        usage = Usage(model_ids=[m for s in samples for m in s.usage.model_ids],
                      calls=self.total(samples, "calls"),
                      input_tokens=self.total(samples, "input_tokens"),
                      output_tokens=self.total(samples, "output_tokens"),
                      estimated_cost_usd=self.total(samples, "estimated_cost_usd"),
                      temperature=samples[0].usage.temperature, seed=samples[0].usage.seed)
        raw = {"samples": [s.model_dump(mode="json") for s in samples]}
        if any(s.status != Status.OK for s in samples):
            return Result(case_id=case.case_id, system=self.name, status=Status.ERROR,
                          usage=usage, raw=raw, error="Incomplete voting panel")
        counts = Counter(s.verdict for s in samples)
        winner, count = counts.most_common(1)[0]
        # Strict majority, including multiway plurality: otherwise gather.
        verdict = winner if count > len(samples)/2 else Verdict.UNDETERMINED
        confidence = count / len(samples)
        return Result(case_id=case.case_id, system=self.name, verdict=verdict,
                      action=action_for(verdict, case), confidence=confidence,
                      reasoning="Count-based strict majority; no majority means GATHER.",
                      disagreement=1-confidence, conflict=len(counts) > 1,
                      confident_consensus=(len(counts) == 1 and
                          min(s.confidence or 0 for s in samples) >= self.consensus_confidence),
                      usage=usage, raw=raw)

    @staticmethod
    def total(samples, field):
        values = [getattr(s.usage, field) for s in samples]
        return None if any(v is None for v in values) else sum(values)
