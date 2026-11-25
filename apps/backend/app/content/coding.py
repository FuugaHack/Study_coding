"""コーディング問題 (Repository → Issue) のコンテンツ。

Git 管理の coding.json を起動時に読み込む。
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr, model_validator

CODING_PATH = Path(__file__).with_name("coding.json")

# サンドボックスで実行できる言語
EXECUTABLE_LANGUAGES = {"python", "javascript", "typescript"}


class Hint(BaseModel):
    level: int
    title: str
    content: str
    closeness: str


class Solution(BaseModel):
    id: str
    title: str
    code: str
    explanation: str = ""
    points: list[str] = Field(default_factory=list)
    is_recommended: bool = False


class CodingTest(BaseModel):
    name: str
    stdin: str = ""
    expected: str
    hidden: bool = False


class Execution(BaseModel):
    # ユーザーコードの後ろに連結して実行する呼び出しコード (stdin の JSON を引数に関数を呼ぶ)
    harness: str
    tests: list[CodingTest] = Field(min_length=1, max_length=20)
    # CI で実行してテストが全て通ることを検証する
    reference_solution: str
    time_limit_s: float = 2.0
    # 使用を禁止する名前 (Python のみ。提出前に構文木で検査する)
    forbidden_names: list[str] = Field(default_factory=list)


class CodingQuestion(BaseModel):
    id: str = Field(max_length=100)
    repository_id: str
    issue_number: int
    title: str
    description: str
    language: str
    framework: str | None = None
    difficulty: Literal["easy", "normal", "hard"]
    type: str
    initial_code: str
    estimated_minutes: int
    tags: list[str] = Field(default_factory=list)
    explanation: str = ""
    hints: list[Hint] = Field(default_factory=list)
    solutions: list[Solution] = Field(default_factory=list)
    execution: Execution | None = None

    @property
    def executable(self) -> bool:
        return self.execution is not None

    @model_validator(mode="after")
    def _check(self) -> CodingQuestion:
        if self.execution and self.language not in EXECUTABLE_LANGUAGES:
            raise ValueError(f"{self.id}: {self.language} はサンドボックスで実行できません")
        levels = [h.level for h in self.hints]
        if levels != sorted(levels) or len(set(levels)) != len(levels):
            raise ValueError(f"{self.id}: ヒントの level は昇順・重複なしにしてください")
        return self


class CodingRepository(BaseModel):
    id: str
    name: str
    description: str
    language: str
    framework: str | None = None
    tags: list[str] = Field(default_factory=list)
    difficulty_range: str
    status: str


class CodingCatalog(BaseModel):
    schema_version: int
    repositories: list[CodingRepository]
    questions: list[CodingQuestion]
    version: str = ""

    _questions_by_id: dict[str, CodingQuestion] = PrivateAttr(default_factory=dict)
    _repos_by_id: dict[str, CodingRepository] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> CodingCatalog:
        repo_ids = {r.id for r in self.repositories}
        qids = [q.id for q in self.questions]
        if len(qids) != len(set(qids)):
            raise ValueError("コーディング問題の ID が重複しています")
        for q in self.questions:
            if q.repository_id not in repo_ids:
                raise ValueError(f"{q.id}: 未知のリポジトリ {q.repository_id}")
        return self

    def model_post_init(self, __context) -> None:
        self._questions_by_id = {q.id: q for q in self.questions}
        self._repos_by_id = {r.id: r for r in self.repositories}

    def get_question(self, question_id: str) -> CodingQuestion | None:
        return self._questions_by_id.get(question_id)

    def get_repository(self, repository_id: str) -> CodingRepository | None:
        return self._repos_by_id.get(repository_id)

    def questions_of(self, repository_id: str) -> list[CodingQuestion]:
        return sorted(
            (q for q in self.questions if q.repository_id == repository_id),
            key=lambda q: q.issue_number,
        )


def load_coding_catalog(path: Path = CODING_PATH) -> CodingCatalog:
    raw = path.read_bytes()
    data = json.loads(raw)
    data["version"] = hashlib.sha256(raw).hexdigest()[:12]
    return CodingCatalog.model_validate(data)


@lru_cache
def get_coding_catalog() -> CodingCatalog:
    return load_coding_catalog()
