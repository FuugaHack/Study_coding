"""Git 管理の学習コンテンツ (JSON) を読み込み・検証する。

コンテンツは起動時に 1 回だけ読み込み、メモリに保持する (ADR-2)。
ファイル内容の SHA-256 先頭 12 文字を `version` とし、回答ログに記録する。
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr, model_validator

CATALOG_PATH = Path(__file__).with_name("catalog.json")

QuestionType = Literal["choice", "multiple-choice", "text", "code"]
QuestionDifficulty = Literal["easy", "normal", "hard"]
CourseCategory = Literal["frontend", "backend", "ai", "database", "infra", "testing", "practice"]
CourseLevel = Literal["beginner", "intermediate", "advanced"]

BLANK_TOKEN = "___"


class Question(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    type: QuestionType
    title: str
    description: str
    difficulty: QuestionDifficulty = "normal"
    choices: list[str] | None = None
    code_template: str | None = None
    answer: str | list[str]
    explanation: str = ""
    # 根拠となる公式ドキュメントなど (任意)。AI 品質レビューに渡す
    references: list[str] = Field(default_factory=list)

    @property
    def answers(self) -> list[str]:
        return self.answer if isinstance(self.answer, list) else [self.answer]

    def content_hash(self) -> str:
        """問題 1 問分の内容ハッシュ。修正されたら変わり、AI レビューが「古い」とみなされる。"""
        canonical = json.dumps(
            self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @model_validator(mode="after")
    def _check_shape(self) -> Question:
        if self.type in ("choice", "multiple-choice"):
            if not self.choices or len(self.choices) < 2:
                raise ValueError(f"{self.id}: choices が 2 つ以上必要です")
            missing = [a for a in self.answers if a not in self.choices]
            if missing:
                raise ValueError(f"{self.id}: 正解 {missing} が choices にありません")
            if self.type == "choice" and len(self.answers) != 1:
                raise ValueError(f"{self.id}: choice の正解は 1 つです")
        if self.type == "code":
            if not self.code_template:
                raise ValueError(f"{self.id}: code_template が必要です")
            blanks = self.code_template.count(BLANK_TOKEN)
            if blanks != len(self.answers):
                raise ValueError(
                    f"{self.id}: 穴の数 ({blanks}) と正解数 ({len(self.answers)}) が一致しません"
                )
        return self


class Course(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    title: str
    description: str
    category: CourseCategory
    level: CourseLevel
    icon: str
    estimated_hours: float
    tags: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    questions: list[Question]


class Catalog(BaseModel):
    schema_version: int
    courses: list[Course]
    version: str = ""

    _course_by_id: dict[str, Course] = PrivateAttr(default_factory=dict)
    _question_index: dict[str, tuple[Course, Question]] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _check_integrity(self) -> Catalog:
        course_ids = [c.id for c in self.courses]
        if len(course_ids) != len(set(course_ids)):
            raise ValueError("コース ID が重複しています")
        question_ids = [q.id for c in self.courses for q in c.questions]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("問題 ID が重複しています")
        known = set(course_ids)
        for c in self.courses:
            unknown = [p for p in c.prerequisites if p not in known]
            if unknown:
                raise ValueError(f"{c.id}: 未知の前提コース {unknown}")
        _assert_acyclic({c.id: c.prerequisites for c in self.courses})
        return self

    # --- lookup helpers (起動後は不変なので dict を都度作らずキャッシュ) ---

    def model_post_init(self, __context) -> None:
        self._course_by_id = {c.id: c for c in self.courses}
        self._question_index = {q.id: (c, q) for c in self.courses for q in c.questions}

    def get_course(self, course_id: str) -> Course | None:
        return self._course_by_id.get(course_id)

    def find_question(self, question_id: str) -> tuple[Course, Question] | None:
        return self._question_index.get(question_id)


def _assert_acyclic(graph: dict[str, list[str]]) -> None:
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node: str, path: list[str]) -> None:
        if node in done:
            return
        if node in visiting:
            raise ValueError(f"前提コースが循環しています: {' -> '.join([*path, node])}")
        visiting.add(node)
        for nxt in graph.get(node, []):
            visit(nxt, [*path, node])
        visiting.discard(node)
        done.add(node)

    for n in graph:
        visit(n, [])


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    raw = path.read_bytes()
    data = json.loads(raw)
    data["version"] = hashlib.sha256(raw).hexdigest()[:12]
    return Catalog.model_validate(data)


@lru_cache
def get_catalog() -> Catalog:
    return load_catalog()
