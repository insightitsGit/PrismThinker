from enum import Enum
import json
from typing import get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from prismthinker import ReasoningContext


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False, validate_assignment=True)


def reject_unknown_fields(value, annotation):
    """Library models can ignore extras; evaluation inputs must never do so."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel) and isinstance(value, dict):
        unknown = set(value) - annotation.model_fields.keys()
        if unknown:
            raise ValueError(f"unknown {annotation.__name__} fields: {sorted(unknown)}")
        for key, item in value.items():
            reject_unknown_fields(item, annotation.model_fields[key].annotation)
    elif get_origin(annotation) is list and isinstance(value, list):
        for item in value:
            reject_unknown_fields(item, get_args(annotation)[0])
    elif get_origin(annotation) is dict and isinstance(value, dict):
        for item in value.values():
            reject_unknown_fields(item, get_args(annotation)[1])
    else:
        for option in get_args(annotation):
            if isinstance(option, type) and issubclass(option, BaseModel):
                reject_unknown_fields(value, option)


class Verdict(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CAUTION = "CAUTION"
    UNDETERMINED = "UNDETERMINED"


class Action(str, Enum):
    EXECUTE = "EXECUTE"
    REFUSE = "REFUSE"
    ESCALATE = "ESCALATE"
    GATHER = "GATHER"
    ANSWER = "ANSWER"


class Source(str, Enum):
    PUBLIC = "public_dataset"
    EXPERT = "expert_authored"
    SYNTHETIC = "synthetic"
    ADVERSARIAL = "adversarial"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class GroundTruth(StrictModel):
    correct_verdict: Verdict
    safe_to_execute: bool
    true_conflict: bool
    requires_human_review: bool
    hard_veto: bool
    answerable: bool
    rationale: str = Field(min_length=1)
    # Legacy v0.1 annotations remain readable; missing is never inferred from a verdict.
    acceptable_directives: list[Action] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def unique_directives(self):
        if self.acceptable_directives is not None and len(set(self.acceptable_directives)) != len(self.acceptable_directives):
            raise ValueError("acceptable directives must be unique")
        return self


class Metadata(StrictModel):
    source: Source
    difficulty: Difficulty
    tags: list[str]
    group_id: str = Field(min_length=1)
    original_id: str = Field(min_length=1)
    provenance: str = Field(min_length=1)


class CaseInput(StrictModel):
    """Only this object crosses into systems; labels and metadata never do."""
    case_id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    context: dict[str, JsonValue]
    evidence: list[dict[str, JsonValue]]
    candidate_action: dict[str, JsonValue]

    def reasoning_context(self) -> ReasoningContext:
        data = dict(self.context)
        data.update(query=self.prompt, domain=self.domain, evidence=self.evidence,
                    hypothesis={"id": self.case_id, "statement": self.prompt,
                                "action": self.candidate_action})
        reject_unknown_fields(data, ReasoningContext)
        return ReasoningContext.model_validate_json(json.dumps(data, allow_nan=False), strict=True)

    @model_validator(mode="after")
    def valid_input(self):
        if set(self.context) & {"query", "domain", "evidence", "hypothesis"}:
            raise ValueError("context cannot shadow canonical input fields")
        self.reasoning_context()
        return self


class EvaluationCase(CaseInput):
    ground_truth: GroundTruth
    metadata: Metadata

    def system_input(self) -> CaseInput:
        return CaseInput.model_validate_json(self.model_dump_json(
            exclude={"ground_truth", "metadata"}))
