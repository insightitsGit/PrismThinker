"""Opt-in boundary for model-proposed actions against server-owned context.

This is an in-process SDK boundary, not network authentication. The host must
authenticate the caller and load the applicable context and tool list itself.
"""
from pydantic import BaseModel, ConfigDict, Field

from prismthinker.adapters.chorusgraph import to_chorusgraph
from prismthinker.core.schemas import CandidateAction, Hypothesis, ReasoningContext


class ActionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=1, max_length=16000)
    action: CandidateAction


def evaluate_proposal(engine, proposal: dict, *, trusted_context: ReasoningContext,
                      allowed_action_names: set[str], allowed_tools: list[str]):
    """Evaluate a proposal without accepting model-supplied policy or authority.

    Consume the returned envelope inside the trusted process. Never deserialize
    a client-supplied envelope and treat its EXECUTE directive as authorization.
    The host remains responsible for validating tool arguments and executing
    exactly the evaluated action, with fresh policy/context at execution time.
    """
    parsed = ActionProposal.model_validate(proposal)
    if parsed.action.name not in allowed_action_names:
        raise ValueError("action is not authorized by the host")
    context = trusted_context.model_copy(deep=True)
    context.query = parsed.statement
    context.hypothesis = Hypothesis(id=parsed.action.id, statement=parsed.statement,
                                    action=parsed.action.model_copy(deep=True))
    return to_chorusgraph(engine.evaluate(context), allowed_tools=list(allowed_tools))
