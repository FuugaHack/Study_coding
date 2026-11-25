"""提出コードの静的チェック (実行前に backend で行う)。"""
from __future__ import annotations

import ast

# 禁止名の検査をすり抜ける手段 (別名で組み込み関数を取り出す) も合わせて禁止する
EVASION_NAMES = frozenset(
    {"builtins", "__builtins__", "__import__", "importlib", "eval", "exec", "getattr",
     "globals", "vars", "compile"}
)


def find_forbidden_python(code: str, forbidden: list[str]) -> list[str]:
    """禁止された名前の使用箇所を返す。構文エラーは実行時に報告させるため空を返す。"""
    if not forbidden:
        return []
    banned = set(forbidden) | EVASION_NAMES
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in banned:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in banned:
            found.add(node.attr)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            for alias in node.names:
                if alias.name.split(".")[0] in banned:
                    found.add(alias.name)
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in banned:
                found.add(node.module or "")
    return sorted(found)
