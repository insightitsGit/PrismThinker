from validation.schemas.case import Verdict
from validation.schemas.result import Action


def action_for(verdict, case):
    if verdict == Verdict.APPROVE:
        return Action.ANSWER if case.candidate_action["kind"] == "assertion" else Action.EXECUTE
    return {Verdict.REJECT: Action.REFUSE, Verdict.CAUTION: Action.ESCALATE,
            Verdict.UNDETERMINED: Action.GATHER}[verdict]
