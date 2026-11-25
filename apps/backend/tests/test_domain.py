"""DB に依存しない純粋ロジックのテスト。"""
import json
from datetime import UTC, date, datetime, timedelta

import pytest

from app.content.loader import Catalog, Question, get_catalog, load_catalog
from app.domain import gamification as g
from app.domain.grading import InvalidAnswerError, grade

# ---------------------------------------------------------------- level


@pytest.mark.parametrize(
    ("xp", "level"),
    [(0, 1), (49, 1), (50, 2), (149, 2), (150, 3), (299, 3), (300, 4), (500, 5)],
)
def test_level_for_xp(xp: int, level: int) -> None:
    assert g.level_for_xp(xp) == level


def test_level_progress() -> None:
    lp = g.level_progress(175)  # L3 (150) → L4 (300)
    assert (lp.level, lp.xp_into_level, lp.xp_for_next_level) == (3, 25, 150)


# ---------------------------------------------------------------- streak

TODAY = date(2026, 11, 25)


def test_streak_starts_at_one() -> None:
    s = g.advance_streak(g.StreakState(0, 0, None), TODAY)
    assert (s.current, s.longest, s.last_active_date) == (1, 1, TODAY)


def test_streak_continues_from_yesterday() -> None:
    s = g.advance_streak(g.StreakState(4, 4, TODAY - timedelta(days=1)), TODAY)
    assert (s.current, s.longest) == (5, 5)


def test_streak_same_day_is_unchanged() -> None:
    state = g.StreakState(3, 7, TODAY)
    assert g.advance_streak(state, TODAY) == state


def test_streak_resets_after_gap_but_keeps_longest() -> None:
    s = g.advance_streak(g.StreakState(9, 9, TODAY - timedelta(days=2)), TODAY)
    assert (s.current, s.longest) == (1, 9)


def test_effective_streak() -> None:
    assert g.effective_streak(g.StreakState(5, 5, TODAY), TODAY) == 5
    assert g.effective_streak(g.StreakState(5, 5, TODAY - timedelta(days=1)), TODAY) == 5
    assert g.effective_streak(g.StreakState(5, 5, TODAY - timedelta(days=2)), TODAY) == 0


def test_local_today_uses_app_timezone() -> None:
    # 2026-11-24 23:30 UTC = 2026-11-25 08:30 JST
    assert g.local_today(datetime(2026, 11, 24, 23, 30, tzinfo=UTC)) == date(2026, 11, 25)


# ---------------------------------------------------------------- quests


def test_daily_quest_progress_is_capped() -> None:
    activity = g.TodayActivity(correct_questions=7, attempted_questions=2, xp_earned=10)
    quest = next(q for q in g.DAILY_QUESTS if q.id == "daily_correct_3")
    assert quest.progress(activity) == 3
    assert quest.is_complete(activity)
    assert not next(q for q in g.DAILY_QUESTS if q.id == "daily_attempt_5").is_complete(activity)


# ---------------------------------------------------------------- grading


def _q(**kw) -> Question:
    base = {"id": "t", "title": "t", "description": "d", "explanation": "e"}
    return Question.model_validate({**base, **kw})


def test_grade_choice() -> None:
    q = _q(type="choice", choices=["a", "b"], answer="b")
    assert grade(q, {"selected": "b"}).outcome == "correct"
    assert grade(q, {"selected": "a"}).outcome == "incorrect"


def test_grade_multiple_choice_requires_exact_set() -> None:
    q = _q(type="multiple-choice", choices=["a", "b", "c"], answer=["a", "c"])
    assert grade(q, {"selected": ["c", "a"]}).outcome == "correct"
    assert grade(q, {"selected": ["a"]}).outcome == "incorrect"
    assert grade(q, {"selected": ["a", "b", "c"]}).outcome == "incorrect"
    assert grade(q, {"selected": ["a", "a", "c"]}).outcome == "incorrect"


def test_grade_code_blanks_trimmed_and_reports_each_blank() -> None:
    q = _q(type="code", code_template="___ f() { ___ g() }", answer=["async", "await"])
    ok = grade(q, {"blanks": [" async ", "await"]})
    assert ok.outcome == "correct" and ok.blank_results == [True, True]
    ng = grade(q, {"blanks": ["async", "wait"]})
    assert ng.outcome == "incorrect" and ng.blank_results == [True, False]


def test_grade_text_is_self_check() -> None:
    q = _q(type="text", answer="sample")
    assert grade(q, {"text": "my answer"}).outcome == "self_check"


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ({"type": "choice", "choices": ["a", "b"], "answer": "a"}, {"selected": ["a"]}),
        ({"type": "code", "code_template": "___", "answer": "x"}, {"blanks": ["x", "y"]}),
        ({"type": "text", "answer": "x"}, {}),
    ],
)
def test_grade_rejects_wrong_answer_shape(question: dict, answer: dict) -> None:
    with pytest.raises(InvalidAnswerError):
        grade(_q(**question), answer)


# ---------------------------------------------------------------- content


def test_bundled_catalog_is_valid() -> None:
    catalog = get_catalog()
    assert len(catalog.courses) >= 28
    assert len(catalog.version) == 12
    roots = [c for c in catalog.courses if not c.prerequisites]
    assert roots, "前提なしで始められるコースが必要"


def test_catalog_rejects_prerequisite_cycle(tmp_path) -> None:
    def course(cid: str, pre: list[str]) -> dict:
        return {
            "id": cid,
            "title": cid,
            "description": "",
            "category": "frontend",
            "level": "beginner",
            "icon": "x",
            "estimated_hours": 1,
            "prerequisites": pre,
            "questions": [],
        }

    path = tmp_path / "c.json"
    path.write_text(
        json.dumps({"schema_version": 1, "courses": [course("a", ["b"]), course("b", ["a"])]})
    )
    with pytest.raises(ValueError, match="循環"):
        load_catalog(path)


def test_catalog_rejects_answer_not_in_choices() -> None:
    with pytest.raises(ValueError, match="choices にありません"):
        _q(type="choice", choices=["a", "b"], answer="z")


def test_catalog_rejects_blank_count_mismatch() -> None:
    with pytest.raises(ValueError, match="穴の数"):
        _q(type="code", code_template="___ ___", answer=["x"])


def test_catalog_lookup() -> None:
    catalog: Catalog = get_catalog()
    course, question = catalog.find_question("q-html-heading")
    assert course.id == "course-html-css" and question.type == "choice"
    assert catalog.find_question("nope") is None
