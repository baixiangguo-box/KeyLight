"""A tiny, safe expression language used by AI-generated lighting effects.

An expression is evaluated once per LED per frame and must return either an
RGB triple ``(r, g, b)`` (0-255) or a single number (used as brightness of
``color``).  Example::

    hsv(0.55 + 0.08*sin(t*0.8 + x*1.2), 0.9, 0.4 + 0.5*sin(t*1.3)**2)

Variables: x, y (0..1 across/down the board), i (led index), row, col, t (s).
Functions: sin cos tan atan2 abs min max sqrt exp log floor ceil round pow
           clamp(v, lo, hi) mod(a, b) smoothstep(a, b, v)
           hsv(h, s, v) rgb(r, g, b) mix(c1, c2, f) grey(v)
"""

from __future__ import annotations

import ast
import math
import operator
import re

ALLOWED_NODES = (
    ast.Expression, ast.Constant, ast.Name, ast.Load,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Call, ast.Tuple, ast.operator, ast.unaryop, ast.boolop, ast.cmpop,
)

COLOR_FUNCS = {"hsv", "rgb", "mix", "grey"}


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _hsv(h, s, v):
    r, g, b = _colorsys_hsv(h % 1.0, _clamp(s, 0.0, 1.0), _clamp(v, 0.0, 1.0))
    return (r * 255.0, g * 255.0, b * 255.0)


def _colorsys_hsv(h, s, v):
    import colorsys
    return colorsys.hsv_to_rgb(h, s, v)


def _rgb(r, g, b):
    return (_clamp(r, 0, 255), _clamp(g, 0, 255), _clamp(b, 0, 255))


def _mix(c1, c2, f):
    f = _clamp(f, 0.0, 1.0)
    return tuple(c1[k] * (1 - f) + c2[k] * f for k in range(3))


def _grey(v):
    v = _clamp(v, 0, 255)
    return (v, v, v)


def _smoothstep(a, b, v):
    if a == b:
        return 0.0 if v < a else 1.0
    t = _clamp((v - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "atan2": math.atan2,
    "abs": abs, "min": min, "max": max, "sqrt": math.sqrt, "exp": math.exp,
    "log": lambda v: math.log(max(v, 1e-6)), "floor": math.floor,
    "ceil": math.ceil, "round": round, "pow": pow, "clamp": _clamp,
    "mod": lambda a, b: a % b if b else 0.0, "smoothstep": _smoothstep,
    "hsv": _hsv, "rgb": _rgb, "mix": _mix, "grey": _grey,
}

CONSTANTS = {"pi": math.pi, "tau": math.tau, "e": math.e}
LIVE_NAMES = {"c1", "c2", "key_on", "key_age", "key_count", "last_col", "last_row",
              "last_age", "last_vk", "pulse", "energy", "beat", "level", "key_release_age"}
LIVE_FUNCS = {"down", "since", "count", "keycol", "keyrow", "released"}


class ExpressionError(ValueError):
    pass


def normalize_expression(source: str) -> str:
    """Accept a common model notation without changing the bounded DSL.

    Functional if(condition, a, b) becomes a lazy Python conditional. The
    normalized expression is what we validate, persist and share.
    """
    if not isinstance(source, str) or len(source) > 2000:
        raise ExpressionError("表达式必须是最多2000字的文本")
    try:
        ast.parse(source, mode="eval")
        return source
    except (SyntaxError, RecursionError):
        if not re.search(r"\bif\s*\(", source):
            return source
    candidate = re.sub(r"\bif\s*\(", "_choose(", source)
    try:
        tree = ast.parse(candidate, mode="eval")
    except (SyntaxError, RecursionError):
        return source
    if len(list(ast.walk(tree))) > 256:
        raise ExpressionError("表达式过于复杂")
    pending = [(tree, 1)]
    while pending:
        node, depth = pending.pop()
        if depth > 24:
            raise ExpressionError("表达式嵌套太深")
        pending.extend((child,depth+1) for child in ast.iter_child_nodes(node))
    class FunctionalIf(ast.NodeTransformer):
        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id == "_choose":
                if len(node.args) != 3 or node.keywords:
                    raise ExpressionError("if(条件,成立值,否则值) 必须有三个参数")
                return ast.copy_location(ast.IfExp(test=node.args[0],body=node.args[1],orelse=node.args[2]),node)
            return node
    normalized = ast.unparse(ast.fix_missing_locations(FunctionalIf().visit(tree)))
    if len(normalized)>2000:
        raise ExpressionError("表达式太长")
    return normalized


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod, ast.Pow: math.pow}
_NAMED_OPS = {cls.__name__: fn for cls, fn in _OPS.items()}


def _number(v):
    if not isinstance(v, (int, float)):
        raise ExpressionError("这里需要数值，颜色请用 mix 混合或调暗，不能直接乘除")
    if not math.isfinite(v) or abs(v) > 1e12:
        raise ExpressionError("表达式必须使用有限数值，绝对值不能超过 1e12")
    return float(v)


def _binary(op, a, b):
    a, b = _number(a), _number(b)
    if op == "Pow" and (abs(a) > 1e6 or abs(b) > 32):
        raise ExpressionError("幂运算超出安全范围")
    return _number(_NAMED_OPS[op](a, b))


class _BoundMath(ast.NodeTransformer):
    def visit_BinOp(self, node):
        self.generic_visit(node)
        return ast.copy_location(ast.Call(func=ast.Name(id="_binary", ctx=ast.Load()),
            args=[ast.Constant(type(node.op).__name__), node.left, node.right], keywords=[]), node)


def _validate(tree: ast.AST, interactive=False) -> None:
    nodes = list(ast.walk(tree))
    if len(nodes) > 256:
        raise ExpressionError("表达式过于复杂")
    def depth(node):
        return 1 + max((depth(c) for c in ast.iter_child_nodes(node)), default=0)
    if depth(tree) > 24:
        raise ExpressionError("表达式嵌套太深")
    for node in nodes:
        if not isinstance(node, ALLOWED_NODES):
            raise ExpressionError(f"不允许的语法: {type(node).__name__}")
        if isinstance(node, ast.BinOp) and type(node.op) not in _OPS:
            raise ExpressionError("不允许的运算符")
        if isinstance(node, ast.Constant):
            _number(node.value)
            if abs(node.value) > 1e6:
                raise ExpressionError("数字常量过大")
        if isinstance(node, ast.Tuple) and len(node.elts) != 3:
            raise ExpressionError("颜色必须包含三个值")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in (FUNCS.keys() | (LIVE_FUNCS if interactive else set())):
                name = getattr(node.func, "id", "?")
                raise ExpressionError(f"不允许的函数: {name}")
            if len(node.args) > 8:
                raise ExpressionError("函数参数太多")
        if isinstance(node, ast.Name) and node.id not in FUNCS and node.id not in CONSTANTS:
            if node.id not in ("x", "y", "i", "row", "col", "t", "n", "cols", "rows") and not (interactive and node.id in LIVE_NAMES | LIVE_FUNCS):
                raise ExpressionError(f"未知变量: {node.id}")


def compile_expression(source: str, *, interactive=False):
    """Compile to ``fn(x, y, i, row, col, t) -> (r, g, b)``."""
    if not isinstance(source, str):
        raise ExpressionError("表达式必须是文本")
    source = source.strip()
    if not source:
        raise ExpressionError("表达式为空")
    if len(source) > 2000:
        raise ExpressionError("表达式太长")
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, RecursionError) as exc:
        raise ExpressionError(f"语法错误: {exc}") from exc
    _validate(tree, interactive)
    tree = ast.fix_missing_locations(_BoundMath().visit(tree))
    code = compile(tree, "<ai-effect>", "eval")
    env = {"__builtins__": {}, **FUNCS, **CONSTANTS, "_binary": _binary,
           "pow": lambda a, b: _binary("Pow", a, b)}

    def fn(x, y, i, row, col, t, cols=22, rows=5, context=None):
        local = dict(x=x, y=y, i=i, row=row, col=col, t=t, n=t, cols=cols, rows=rows)
        if interactive:
            local.update({name: 0.0 for name in LIVE_NAMES})
            local.update(c1=(255,90,60), c2=(30,123,255), key_age=1e6, last_age=1e6, key_release_age=1e6,
                         down=lambda vk: 0, since=lambda vk: 1e6, count=lambda vk: 0,
                         released=lambda vk: 1e6,
                         keycol=lambda vk: -100, keyrow=lambda vk: -100)
            local.update({k:v for k,v in (context or {}).items() if k in LIVE_NAMES | LIVE_FUNCS})
        try:
            value = eval(code, env, local)  # noqa: S307 - bounded AST above
            if isinstance(value, tuple):
                return tuple(_clamp(_number(c), 0, 255) for c in value)
            v = _number(value)
            if 0.0 <= v <= 1.0:
                v *= 255
            return (_clamp(v, 0, 255),) * 3
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ExpressionError(f"表达式无法运行: {exc}") from exc

    for rows in (5, 6):
        for x, y in ((0, 0), (0.5, 0.5), (1, 1)):
            for t in (0, 0.7, 3.1):
                fn(x, y, int(y*(rows-1))*22+int(x*21), int(y*(rows-1)), int(x*21), t, rows=rows)
    return fn


DSL_GUIDE = """\
可用变量: x(0..1 从左到右), y(0..1 从上到下), i(灯珠序号 0..131), row(0..4), col(0..21), t(秒)
可用函数: sin cos tan atan2 abs min max sqrt exp log floor ceil round pow
          clamp(v,lo,hi) mod(a,b) smoothstep(a,b,v)
          hsv(h,s,v) rgb(r,g,b) mix(颜色1,颜色2,比例) grey(v)
表达式返回 (r,g,b) 三元组，或 0..1 的数字（当作亮度）。
示例:
  hsv(0.55 + 0.08*sin(t*0.8 + x*1.2), 0.9, 0.35 + 0.6*(0.5+0.5*sin(t*1.3)))
  mix(rgb(255,80,0), rgb(0,60,255), 0.5+0.5*sin(x*6 - t*2))
"""
