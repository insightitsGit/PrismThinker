from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from typing import Any, Optional

_ALLOWED_NODES = (
    ast.Expression,
    ast.Expr,
    ast.Constant,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Pow,
    ast.UAdd,
    ast.USub,
    ast.Load,
)

_FORBIDDEN_OPS = (ast.Mod, ast.BitAnd, ast.BitOr, ast.MatMult)

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
}

_UNOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


@dataclass(frozen=True)
class FastPathAttempt:
    eligible: bool
    value: Any = None
    division_by_zero: bool = False
    math_shaped: bool = False
    reason: str = ""


class _Whitelist(ast.NodeVisitor):
    def __init__(self) -> None:
        self.ok = True
        self.has_name = False
        self.has_mod = False

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, _FORBIDDEN_OPS):
            self.ok = False
            if isinstance(node, ast.Mod):
                self.has_mod = True
            return
        if not isinstance(node, _ALLOWED_NODES):
            if isinstance(node, ast.Name):
                self.has_name = True
            self.ok = False
            return
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            self.ok = False
            return
        super().generic_visit(node)


def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNOPS:
        return _UNOPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, (ast.Div, ast.FloorDiv)) and right == 0:
            raise ZeroDivisionError
        return _BINOPS[type(node.op)](left, right)
    raise ValueError("disallowed node during evaluation")


def probe_expression(query: str) -> FastPathAttempt:
    text = query.strip()
    if not text:
        return FastPathAttempt(False, reason="empty")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return FastPathAttempt(False, reason="syntax")

    walker = _Whitelist()
    walker.visit(tree)
    math_shaped = walker.has_name or walker.has_mod
    if not walker.ok:
        return FastPathAttempt(False, math_shaped=math_shaped, reason="whitelist")

    try:
        value = _eval_node(tree)
    except ZeroDivisionError:
        return FastPathAttempt(False, division_by_zero=True, math_shaped=True, reason="div0")
    except Exception:
        return FastPathAttempt(False, reason="eval")

    return FastPathAttempt(True, value=value)
