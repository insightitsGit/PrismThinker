"""Shared predicate parser. Not an evaluator and not a decision procedure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from prismthinker.core.schemas import CandidateAction, FactValue
from prismthinker.reason_codes import REASON_UNBOUND_PATH

UNBOUND = object()


class PredicateError(ValueError):
    pass


@dataclass(frozen=True)
class PredicateResult:
    value: Optional[bool]
    unbound: bool
    cited_fact_keys: tuple[str, ...]
    error: Optional[str] = None


@dataclass(frozen=True)
class _Tok:
    kind: str
    value: Any
    pos: int


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_cont(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _tokenize(source: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch.isspace():
            i += 1
            continue
        if source.startswith("==", i):
            tokens.append(_Tok("OP", "==", i))
            i += 2
            continue
        if source.startswith("!=", i):
            tokens.append(_Tok("OP", "!=", i))
            i += 2
            continue
        if source.startswith("<=", i):
            tokens.append(_Tok("OP", "<=", i))
            i += 2
            continue
        if source.startswith(">=", i):
            tokens.append(_Tok("OP", ">=", i))
            i += 2
            continue
        if ch == "<":
            tokens.append(_Tok("OP", "<", i))
            i += 1
            continue
        if ch == ">":
            tokens.append(_Tok("OP", ">", i))
            i += 1
            continue
        if ch == "(":
            tokens.append(_Tok("LPAREN", "(", i))
            i += 1
            continue
        if ch == ")":
            tokens.append(_Tok("RPAREN", ")", i))
            i += 1
            continue
        if ch == "[":
            tokens.append(_Tok("LBRACK", "[", i))
            i += 1
            continue
        if ch == "]":
            tokens.append(_Tok("RBRACK", "]", i))
            i += 1
            continue
        if ch == ",":
            tokens.append(_Tok("COMMA", ",", i))
            i += 1
            continue
        if ch == ".":
            tokens.append(_Tok("DOT", ".", i))
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            j = i + 1
            buf: list[str] = []
            while j < n and source[j] != quote:
                if source[j] == "\\" and j + 1 < n:
                    buf.append(source[j + 1])
                    j += 2
                    continue
                buf.append(source[j])
                j += 1
            if j >= n:
                raise PredicateError(f"unterminated string at {i}")
            tokens.append(_Tok("STRING", "".join(buf), i))
            i = j + 1
            continue
        if ch.isdigit() or (ch == "-" and i + 1 < n and source[i + 1].isdigit()):
            j = i + 1 if ch == "-" else i
            while j < n and (source[j].isdigit() or source[j] == "."):
                j += 1
            raw = source[i:j]
            number: float | int
            if "." in raw:
                number = float(raw)
            else:
                number = int(raw)
            tokens.append(_Tok("NUMBER", number, i))
            i = j
            continue
        if _is_ident_start(ch):
            j = i + 1
            while j < n and _is_ident_cont(source[j]):
                j += 1
            word = source[i:j]
            low = word.lower()
            if low == "and":
                tokens.append(_Tok("AND", "and", i))
            elif low == "or":
                tokens.append(_Tok("OR", "or", i))
            elif low == "not":
                tokens.append(_Tok("NOT", "not", i))
            elif low == "in":
                tokens.append(_Tok("OP", "in", i))
            elif low == "true":
                tokens.append(_Tok("BOOL", True, i))
            elif low == "false":
                tokens.append(_Tok("BOOL", False, i))
            else:
                tokens.append(_Tok("IDENT", word, i))
            i = j
            continue
        raise PredicateError(f"unexpected character {ch!r} at {i}")
    tokens.append(_Tok("EOF", None, n))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Tok]) -> None:
        self.tokens = tokens
        self.i = 0

    def _peek(self) -> _Tok:
        return self.tokens[self.i]

    def _eat(self, kind: Optional[str] = None) -> _Tok:
        tok = self.tokens[self.i]
        if kind is not None and tok.kind != kind:
            raise PredicateError(f"expected {kind}, got {tok.kind} at {tok.pos}")
        self.i += 1
        return tok

    def parse(self) -> Any:
        node = self._or()
        if self._peek().kind != "EOF":
            raise PredicateError(f"trailing input at {self._peek().pos}")
        return node

    def _or(self) -> Any:
        left = self._and()
        while self._peek().kind == "OR":
            self._eat("OR")
            left = ("or", left, self._and())
        return left

    def _and(self) -> Any:
        left = self._cmp()
        while self._peek().kind == "AND":
            self._eat("AND")
            left = ("and", left, self._cmp())
        return left

    def _cmp(self) -> Any:
        if self._peek().kind == "NOT":
            self._eat("NOT")
            return ("not", self._cmp())
        if self._peek().kind == "LPAREN":
            self._eat("LPAREN")
            node = self._or()
            self._eat("RPAREN")
            return node
        path = self._path()
        op = self._eat("OP")
        value = self._value()
        return ("cmp", path, op.value, value)

    def _path(self) -> str:
        first = self._eat("IDENT")
        parts = [first.value]
        while self._peek().kind == "DOT":
            self._eat("DOT")
            parts.append(self._eat("IDENT").value)
        path = ".".join(parts)
        if path == "action.name":
            return path
        if path.startswith("fact.") and path.count(".") == 1:
            return path
        if path.startswith("action.payload.") and path.count(".") == 2:
            return path
        raise PredicateError(f"illegal path {path!r}")

    def _value(self) -> Any:
        tok = self._peek()
        if tok.kind == "NUMBER":
            return self._eat().value
        if tok.kind == "BOOL":
            return self._eat().value
        if tok.kind == "STRING":
            return self._eat().value
        if tok.kind == "IDENT":
            return self._eat().value
        if tok.kind == "LBRACK":
            return self._list()
        raise PredicateError(f"expected value at {tok.pos}")

    def _list(self) -> list[Any]:
        self._eat("LBRACK")
        items: list[Any] = []
        if self._peek().kind == "RBRACK":
            self._eat("RBRACK")
            return items
        items.append(self._value())
        while self._peek().kind == "COMMA":
            self._eat("COMMA")
            items.append(self._value())
        self._eat("RBRACK")
        return items


def parse_predicate(source: str) -> Any:
    return _Parser(_tokenize(source)).parse()


def resolve_path(
    path: str,
    facts: dict[str, FactValue],
    action: Optional[CandidateAction],
) -> Any:
    if path.startswith("fact."):
        key = path[5:]
        if key not in facts:
            return UNBOUND
        return facts[key].value
    if path == "action.name":
        if action is None:
            return UNBOUND
        return action.name
    if path.startswith("action.payload."):
        key = path[len("action.payload.") :]
        if action is None or key not in action.payload:
            return UNBOUND
        return action.payload[key]
    return UNBOUND


def _collect_fact_keys(node: Any) -> list[str]:
    if isinstance(node, tuple):
        if node[0] == "cmp":
            path = node[1]
            return [path[5:]] if path.startswith("fact.") else []
        keys: list[str] = []
        for child in node[1:]:
            keys.extend(_collect_fact_keys(child))
        return keys
    return []


def _compare(op: str, left: Any, right: Any) -> bool:
    if op == "in":
        if not isinstance(right, list):
            raise PredicateError("'in' requires a list")
        return left in right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    try:
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
    except TypeError as exc:
        raise PredicateError(f"incomparable values {left!r} {op} {right!r}") from exc
    raise PredicateError(f"unknown operator {op}")


def _eval_node(
    node: Any,
    facts: dict[str, FactValue],
    action: Optional[CandidateAction],
) -> Any:
    if isinstance(node, tuple):
        kind = node[0]
        if kind == "or":
            left = _eval_node(node[1], facts, action)
            if left is UNBOUND:
                return UNBOUND
            if left is True:
                return True
            return _eval_node(node[2], facts, action)
        if kind == "and":
            left = _eval_node(node[1], facts, action)
            if left is UNBOUND:
                return UNBOUND
            if left is False:
                return False
            return _eval_node(node[2], facts, action)
        if kind == "not":
            inner = _eval_node(node[1], facts, action)
            if inner is UNBOUND:
                return UNBOUND
            return not inner
        if kind == "cmp":
            _, path, op, value = node
            bound = resolve_path(path, facts, action)
            if bound is UNBOUND:
                return UNBOUND
            return _compare(op, bound, value)
    raise PredicateError("invalid predicate node")


def evaluate_predicate(
    source: str,
    facts: dict[str, FactValue],
    action: Optional[CandidateAction],
) -> PredicateResult:
    try:
        tree = parse_predicate(source)
    except PredicateError as exc:
        return PredicateResult(None, False, (), str(exc))
    cited = tuple(dict.fromkeys(_collect_fact_keys(tree)))
    try:
        value = _eval_node(tree, facts, action)
    except PredicateError as exc:
        return PredicateResult(None, False, cited, str(exc))
    if value is UNBOUND:
        return PredicateResult(None, True, cited, REASON_UNBOUND_PATH)
    return PredicateResult(bool(value), False, cited, None)
