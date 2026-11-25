"""カタログ問題のサーバー採点 (客観判定のみ。AI は使わない)。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.content.loader import Question

GradeOutcome = Literal["correct", "incorrect", "self_check"]


class InvalidAnswerError(ValueError):
    """問題タイプに合わない回答形式。"""


@dataclass(frozen=True)
class GradeResult:
    outcome: GradeOutcome
    # code 型のみ: 穴ごとの正誤 (正解そのものは返さずに「どこが違うか」を伝えるヒント)
    blank_results: list[bool] = field(default_factory=list)


def _normalize(value: str) -> str:
    return value.strip()


def grade(question: Question, answer: dict) -> GradeResult:
    qtype = question.type

    if qtype == "choice":
        selected = answer.get("selected")
        if not isinstance(selected, str):
            raise InvalidAnswerError("selected (文字列) が必要です")
        ok = selected == question.answers[0]
        return GradeResult("correct" if ok else "incorrect")

    if qtype == "multiple-choice":
        selected = answer.get("selected")
        if not isinstance(selected, list) or not all(isinstance(s, str) for s in selected):
            raise InvalidAnswerError("selected (文字列の配列) が必要です")
        ok = set(selected) == set(question.answers) and len(selected) == len(set(selected))
        return GradeResult("correct" if ok else "incorrect")

    if qtype == "code":
        blanks = answer.get("blanks")
        expected = question.answers
        if (
            not isinstance(blanks, list)
            or not all(isinstance(b, str) for b in blanks)
            or len(blanks) != len(expected)
        ):
            raise InvalidAnswerError(f"blanks (文字列 {len(expected)} 個の配列) が必要です")
        results = [_normalize(b) == _normalize(e) for b, e in zip(blanks, expected, strict=True)]
        return GradeResult("correct" if all(results) else "incorrect", blank_results=results)

    if qtype == "text":
        text = answer.get("text")
        if not isinstance(text, str):
            raise InvalidAnswerError("text (文字列) が必要です")
        # 記述式は自己チェック (docs/ai-question-platform.md §8 の方針を踏襲)
        return GradeResult("self_check")

    raise InvalidAnswerError(f"未対応の問題タイプ: {qtype}")
