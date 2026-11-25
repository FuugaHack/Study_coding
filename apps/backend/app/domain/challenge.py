"""コースチャレンジ (実力テスト / ボス戦) の純粋ロジック。

- 実力テスト (placement): 経験者向け。未クリア (ロック中を含む) のコースで受験でき、
  合格するとそのコースと前提コースすべてをクリア扱いにする (飛び級)。
- ボス戦 (boss): コースをクリア (70%) した後の総合問題。合格で 👑 と報酬。

どちらも自動採点できる問題 (text 以外) からランダムに出題し、80% 以上で合格。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

from app.content.loader import Catalog, Course, Question

ChallengeMode = Literal["placement", "boss"]

PASS_RATIO = 0.8
MIN_QUESTIONS = 2
QUESTION_COUNT: dict[str, int] = {"placement": 5, "boss": 8}
SECONDS_PER_QUESTION: dict[str, int] = {"placement": 90, "boss": 60}
# 通信遅延などを考慮した提出の猶予
SUBMIT_GRACE_SECONDS = 15

BOSS_XP = 50
BOSS_COINS = 20
PLACEMENT_XP = 30


@dataclass(frozen=True)
class ChallengeScore:
    correct: int
    total: int

    @property
    def percent(self) -> int:
        return round(self.correct / self.total * 100) if self.total else 0

    @property
    def passed(self) -> bool:
        return self.total > 0 and self.correct / self.total >= PASS_RATIO


def gradeable_questions(course: Course) -> list[Question]:
    return [q for q in course.questions if q.type != "text"]


def is_available(course: Course) -> bool:
    return len(gradeable_questions(course)) >= MIN_QUESTIONS


def select_questions(
    course: Course, mode: ChallengeMode, rng: random.Random | None = None
) -> list[Question]:
    pool = gradeable_questions(course)
    count = min(QUESTION_COUNT[mode], len(pool))
    return (rng or random.Random()).sample(pool, count)


def time_limit_seconds(mode: ChallengeMode, question_count: int) -> int:
    return SECONDS_PER_QUESTION[mode] * question_count


def ancestors(catalog: Catalog, course_id: str) -> set[str]:
    """course_id の前提コースを再帰的にすべて返す (自身は含まない)。"""
    seen: set[str] = set()
    stack = list(catalog.get_course(course_id).prerequisites)
    while stack:
        cid = stack.pop()
        if cid in seen:
            continue
        seen.add(cid)
        stack.extend(catalog.get_course(cid).prerequisites)
    return seen


def boss_key(course_id: str) -> str:
    return f"boss:{course_id}"


def placement_key(course_id: str) -> str:
    return f"placement:{course_id}"
