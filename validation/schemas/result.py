from enum import Enum
from pydantic import Field, JsonValue, model_validator
from validation.schemas.case import StrictModel, Verdict, Action


class Status(str, Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class Usage(StrictModel):
    model_ids: list[str] = Field(default_factory=list)
    calls: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    temperature: float | None = None
    seed: int | None = None


class Result(StrictModel):
    case_id: str
    system: str
    status: Status = Status.OK
    verdict: Verdict | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    reasoning: str = ""
    action: Action | None = None
    conflict: bool | None = None
    hard_veto: bool | None = None
    confident_consensus: bool | None = None
    delta: float | None = Field(default=None, ge=0, le=1)
    uncertainty: float | None = Field(default=None, ge=0, le=1)
    disagreement: float | None = Field(default=None, ge=0, le=1)
    latency_ms: float = Field(default=0.0, ge=0)
    usage: Usage = Field(default_factory=Usage)
    raw: dict[str, JsonValue] = Field(default_factory=dict)
    error: str | None = None

    @model_validator(mode="after")
    def complete(self):
        if self.status == Status.OK and (self.verdict is None or self.action is None):
            raise ValueError("successful results need verdict and action")
        if self.status != Status.OK and self.action is not None:
            raise ValueError("failed calls must not fabricate an action")
        return self
