import ast
import json
import math
import operator
import sys


_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}

_CMPOPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

_FUNCS = {
    "abs": abs,
    "min": min,
    "max": max,
    "pow": pow,
    "round": round,
    "sqrt": math.sqrt,
    "floor": math.floor,
    "ceil": math.ceil,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
}


def _evaluate(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise ValueError("不支持的常量")
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise ValueError("不支持的运算符")
        return op(_evaluate(node.left), _evaluate(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _UNARYOPS.get(type(node.op))
        if op is None:
            raise ValueError("不支持的运算符")
        return op(_evaluate(node.operand))
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left)
        for op_node, comparator in zip(node.ops, node.comparators):
            op = _CMPOPS.get(type(op_node))
            if op is None:
                raise ValueError("不支持的比较符")
            if not op(left, _evaluate(comparator)):
                return False
            left = _evaluate(comparator)
        return True
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for value in node.values:
                if not _evaluate(value):
                    return False
            return True
        for value in node.values:
            if _evaluate(value):
                return True
        return False
    if isinstance(node, ast.IfExp):
        return _evaluate(node.body if _evaluate(node.test) else node.orelse)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("不支持的函数")
        name = node.func.id
        func = _FUNCS.get(name)
        if func is None:
            raise ValueError(f"不允许调用函数 {name}")
        args = [_evaluate(arg) for arg in node.args]
        if node.keywords:
            raise ValueError("不支持关键字参数")
        return func(*args)
    if isinstance(node, ast.Name):
        if node.id == "pi":
            return math.pi
        if node.id == "e":
            return math.e
        raise ValueError(f"不允许使用变量 {node.id}")
    raise ValueError("表达式包含不支持的内容")


def main() -> None:
    data = json.load(sys.stdin)
    params = data.get("params") or {}
    expression = str(params.get("expression") or "").strip()
    if not expression:
        print(json.dumps({"success": False, "message": "表达式不能为空"}))
        return
    if len(expression) > 500:
        print(json.dumps({"success": False, "message": "表达式过长"}))
        return
    try:
        tree = ast.parse(expression, mode="eval")
        result = _evaluate(tree)
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"计算失败: {exc}"},
                ensure_ascii=False,
            )
        )
        return
    if isinstance(result, float) and not math.isfinite(result):
        result = str(result)
    print(
        json.dumps(
            {
                "success": True,
                "message": "计算完成",
                "result": result,
                "content": json.dumps(
                    {"result": result}, ensure_ascii=False
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
