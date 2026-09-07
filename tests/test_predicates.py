from __future__ import annotations

import pytest

from prismthinker.core.predicates import (
    UNBOUND,
    PredicateError,
    _compare,
    _collect_fact_keys,
    _eval_node,
    evaluate_predicate,
    parse_predicate,
    resolve_path,
)
from prismthinker.core.schemas import ActionKind, CandidateAction, FactValue
from prismthinker.reason_codes import REASON_UNBOUND_PATH


def _facts(**values: object) -> dict[str, FactValue]:
    return {key: FactValue(key=key, value=value) for key, value in values.items()}


def _action(**payload: object) -> CandidateAction:
    return CandidateAction(
        id="a1",
        kind=ActionKind.TOOL_INVOCATION,
        name="issue_refund",
        payload=dict(payload),
    )


def test_nested_boolean_and_comparisons() -> None:
    result = evaluate_predicate(
        "fact.a == 1 and (fact.b == 2 or not fact.c == true)",
        _facts(a=1, b=2, c=False),
        None,
    )
    assert result.value is True
    assert result.unbound is False
    assert result.cited_fact_keys == ("a", "b", "c")
    facts = _facts(a=1, c=False)
    assert evaluate_predicate("fact.a == 0 or fact.a == 1", facts, None).value is True
    assert evaluate_predicate("not fact.a == 0", facts, None).value is True
    assert evaluate_predicate("fact.c == false", facts, None).value is True


def test_inequalities_and_in_list() -> None:
    facts = _facts(n=10, color="red")
    assert evaluate_predicate("fact.n > 3", facts, None).value is True
    assert evaluate_predicate("fact.n >= 10", facts, None).value is True
    assert evaluate_predicate("fact.n < 11", facts, None).value is True
    assert evaluate_predicate("fact.n <= 10", facts, None).value is True
    assert evaluate_predicate("fact.n != 9", facts, None).value is True
    assert evaluate_predicate("fact.n in [10, 20]", facts, None).value is True
    assert evaluate_predicate("fact.n in []", facts, None).value is False
    assert evaluate_predicate("fact.color == red", facts, None).value is True


def test_strings_escapes_and_floats() -> None:
    facts = _facts(label='a"b', x=1.5)
    assert evaluate_predicate('fact.label == "a\\"b"', facts, None).value is True
    assert evaluate_predicate("fact.x >= 1.5", facts, None).value is True


def test_action_name_and_payload() -> None:
    action = _action(amount=750)
    assert evaluate_predicate('action.name == "issue_refund"', {}, action).value is True
    assert evaluate_predicate("action.payload.amount > 500", {}, action).value is True
    missing = evaluate_predicate("action.payload.amount > 500", {}, None)
    assert missing.unbound is True
    assert missing.error == REASON_UNBOUND_PATH
    no_key = evaluate_predicate("action.payload.other == 1", {}, action)
    assert no_key.unbound is True
    nameless = evaluate_predicate('action.name == "x"', {}, None)
    assert nameless.unbound is True


def test_unbound_fact_and_or_short_circuit() -> None:
    facts = _facts(a=1)
    missing = evaluate_predicate("fact.missing == 1", facts, None)
    assert missing.unbound is True
    assert missing.value is None
    true_or = evaluate_predicate("fact.a == 1 or fact.missing == 1", facts, None)
    assert true_or.value is True
    false_and = evaluate_predicate("fact.a == 0 and fact.missing == 1", facts, None)
    assert false_and.value is False
    unbound_or = evaluate_predicate("fact.missing == 1 or fact.a == 1", facts, None)
    assert unbound_or.unbound is True
    unbound_and = evaluate_predicate("fact.missing == 1 and fact.a == 1", facts, None)
    assert unbound_and.unbound is True
    not_unbound = evaluate_predicate("not fact.missing == 1", facts, None)
    assert not_unbound.unbound is True


def test_negative_numbers_quotes_and_list_items() -> None:
    facts = _facts(n=-3, tag="ok")
    assert evaluate_predicate("fact.n == -3", facts, None).value is True
    assert evaluate_predicate("fact.tag == 'ok'", facts, None).value is True
    assert evaluate_predicate("fact.n in [-3, 0, 1]", facts, None).value is True
    assert evaluate_predicate("fact.n != 0", facts, None).value is True


def test_unknown_tuple_kind_is_invalid_node() -> None:
    with pytest.raises(PredicateError, match="invalid predicate node"):
        _eval_node(("nope",), {}, None)


def test_parse_errors_are_predicate_results() -> None:
    cases = [
        "fact.a == 1 @ 2",
        'fact.a == "unterminated',
        "fact.a ==",
        "fact.a.b == 1",
        "action.payload == 1",
        "foo.bar == 1",
        "fact.a == 1 extra",
        "(fact.a == 1",
    ]
    for source in cases:
        result = evaluate_predicate(source, _facts(a=1), None)
        assert result.value is None
        assert result.unbound is False
        assert result.error


def test_in_requires_a_list() -> None:
    result = evaluate_predicate("fact.n in 3", _facts(n=3), None)
    assert result.error
    assert "in" in (result.error or "")


def test_incomparable_values() -> None:
    result = evaluate_predicate("fact.s > 1", _facts(s="hello"), None)
    assert result.error
    assert "incomparable" in (result.error or "")


def test_illegal_and_unknown_paths() -> None:
    with pytest.raises(PredicateError, match="illegal path"):
        parse_predicate("action.foo == 1")
    assert resolve_path("not.a.path", {}, None) is UNBOUND
    assert resolve_path("fact.gone", {}, None) is UNBOUND


def test_compare_unknown_operator_and_invalid_node() -> None:
    with pytest.raises(PredicateError, match="unknown operator"):
        _compare("??", 1, 2)
    with pytest.raises(PredicateError, match="invalid predicate node"):
        _eval_node("not-a-node", {}, None)
    assert _collect_fact_keys(0) == []
    tree = parse_predicate("action.payload.amount > 1")
    assert _collect_fact_keys(tree) == []
