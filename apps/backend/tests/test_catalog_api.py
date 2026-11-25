"""カタログ API + ゲーミフィケーションの結合テスト (実 PostgreSQL)。"""
import json
from datetime import timedelta

from httpx import AsyncClient

from app.content.loader import get_catalog
from app.domain import gamification as g
from app.repositories.gamification_repository import GamificationRepository
from app.services.gamification_service import GamificationService

API = "/api/v1"


def _correct_payload(question_id: str) -> dict:
    _, q = get_catalog().find_question(question_id)
    if q.type == "choice":
        return {"selected": q.answers[0]}
    if q.type == "multiple-choice":
        return {"selected": q.answers}
    if q.type == "code":
        return {"blanks": q.answers}
    return {"text": "自分の答え"}


async def _answer(client: AsyncClient, qid: str, payload: dict | None = None) -> dict:
    res = await client.post(
        f"{API}/catalog/questions/{qid}/answer", json=payload or _correct_payload(qid)
    )
    assert res.status_code == 200, res.text
    return res.json()


async def test_requires_auth(client: AsyncClient) -> None:
    assert (await client.get(f"{API}/catalog/courses")).status_code in (401, 403)


async def test_course_list_has_no_answers_and_locks(auth_client: AsyncClient) -> None:
    res = await auth_client.get(f"{API}/catalog/courses")
    assert res.status_code == 200
    body = res.json()
    courses = {c["id"]: c for c in body["courses"]}
    assert courses["course-html-css"]["status"] == "not-started"
    assert courses["course-typescript"]["is_locked"] is True
    assert courses["course-typescript"]["prerequisite_titles"] == ["JavaScript 入門"]
    assert "answer" not in json.dumps(body)


async def test_course_detail_hides_answers(auth_client: AsyncClient) -> None:
    res = await auth_client.get(f"{API}/catalog/courses/course-javascript")
    assert res.status_code == 200
    for q in res.json()["questions"]:
        assert "answer" not in q and "explanation" not in q
        if q["type"] == "code":
            assert q["blank_count"] >= 1


async def test_unknown_course_and_question_404(auth_client: AsyncClient) -> None:
    assert (await auth_client.get(f"{API}/catalog/courses/nope")).status_code == 404
    res = await auth_client.post(f"{API}/catalog/questions/nope/answer", json={"selected": "x"})
    assert res.status_code == 404


async def test_correct_answer_awards_xp_once(auth_client: AsyncClient) -> None:
    first = await _answer(auth_client, "q-html-heading")
    assert first["result"] == "correct"
    assert first["correct_answer"] == "<h1>"
    assert first["reward"]["xp_gained"] == g.FIRST_CORRECT_XP["easy"]
    assert first["stats"]["current_streak"] == 1
    assert first["stats"]["studied_today"] is True

    # 同じ日の再正解は復習 XP (2) のみ、3 回目は 0
    second = await _answer(auth_client, "q-html-heading")
    assert second["reward"]["xp_gained"] == g.REVIEW_XP
    third = await _answer(auth_client, "q-html-heading")
    assert third["reward"]["xp_gained"] == 0
    assert third["stats"]["total_xp"] == g.FIRST_CORRECT_XP["easy"] + g.REVIEW_XP


async def test_incorrect_answer_hides_solution_until_second_miss(auth_client: AsyncClient) -> None:
    wrong = {"selected": "<p>"}
    first = await _answer(auth_client, "q-html-heading", wrong)
    assert first["result"] == "incorrect"
    assert first["correct_answer"] is None and first["explanation"] is None
    assert first["reward"]["xp_gained"] == 0

    second = await _answer(auth_client, "q-html-heading", wrong)
    assert second["correct_answer"] == "<h1>"
    assert second["explanation"]

    # 正解を見た後の初回正解は満額にしない (復習扱い)
    after = await _answer(auth_client, "q-html-heading")
    assert after["result"] == "correct"
    assert after["reward"]["xp_gained"] == g.REVIEW_XP


async def test_code_answer_reports_blank_results(auth_client: AsyncClient) -> None:
    res = await _answer(auth_client, "q-js-async-await", {"blanks": ["async", "wait"]})
    assert res["result"] == "incorrect"
    assert res["blank_results"] == [True, False]


async def test_text_self_check(auth_client: AsyncClient) -> None:
    html = get_catalog().get_course("course-html-css")
    qid = next(q.id for q in html.questions if q.type == "text")

    # 空欄で解答例だけ見る → 解答例は見られるが XP なし・未解決
    peek = await _answer(auth_client, qid, {"text": "  "})
    assert peek["result"] == "self_check" and peek["correct_answer"]
    assert peek["reward"]["xp_gained"] == 0
    # 覗き見は回答として記録しない (クエスト「挑戦」にも数えない)
    quest = next(q for q in peek["stats"]["daily_quests"] if q["id"] == "daily_attempt_5")
    assert quest["progress"] == 0
    detail = (await auth_client.get(f"{API}/catalog/courses/course-html-css")).json()
    assert next(q for q in detail["questions"] if q["id"] == qid)["solved"] is False

    answered = await _answer(auth_client, qid, {"text": "自分なりの説明"})
    assert answered["reward"]["xp_gained"] == g.SELF_CHECK_XP
    detail = (await auth_client.get(f"{API}/catalog/courses/course-html-css")).json()
    assert next(q for q in detail["questions"] if q["id"] == qid)["solved"] is True


async def test_concurrent_answers_do_not_double_award(auth_client: AsyncClient) -> None:
    import asyncio

    results = await asyncio.gather(*(_answer(auth_client, "q-html-heading") for _ in range(5)))
    stats = (await auth_client.get(f"{API}/gamification/me")).json()
    gained = sum(r["reward"]["xp_gained"] for r in results)
    assert stats["total_xp"] == gained == g.FIRST_CORRECT_XP["easy"] + g.REVIEW_XP


async def test_invalid_answer_shape_is_422(auth_client: AsyncClient) -> None:
    res = await auth_client.post(
        f"{API}/catalog/questions/q-html-heading/answer", json={"blanks": ["x"]}
    )
    assert res.status_code == 422


async def test_locked_course_rejects_answers_until_prerequisite_cleared(
    auth_client: AsyncClient,
) -> None:
    ts_question = get_catalog().get_course("course-typescript").questions[0].id
    res = await auth_client.post(
        f"{API}/catalog/questions/{ts_question}/answer", json=_correct_payload(ts_question)
    )
    assert res.status_code == 403

    js = get_catalog().get_course("course-javascript")
    for q in js.questions[: -(-len(js.questions) * 7 // 10)]:  # 70% 以上 (切り上げ)
        await _answer(auth_client, q.id)

    listing = (await auth_client.get(f"{API}/catalog/courses")).json()
    courses = {c["id"]: c for c in listing["courses"]}
    assert courses["course-typescript"]["is_locked"] is False
    assert courses["course-javascript"]["status"] == "in-progress"
    await _answer(auth_client, ts_question)


async def test_course_completion_status(auth_client: AsyncClient) -> None:
    course = get_catalog().get_course("course-python")
    for q in course.questions:
        await _answer(auth_client, q.id)
    detail = (await auth_client.get(f"{API}/catalog/courses/course-python")).json()
    assert detail["status"] == "completed" and detail["progress"] == 100
    assert all(q["solved"] for q in detail["questions"])


async def test_daily_quests_complete_once(auth_client: AsyncClient) -> None:
    html = get_catalog().get_course("course-html-css")
    choice_ids = [q.id for q in html.questions if q.type == "choice"][:3]
    results = [await _answer(auth_client, qid) for qid in choice_ids]

    completed = [q["id"] for r in results for q in r["reward"]["completed_quests"]]
    assert completed.count("daily_correct_3") == 1
    assert results[-1]["reward"]["coins_gained"] >= g.QUEST_COINS

    stats = (await auth_client.get(f"{API}/gamification/me")).json()
    quest = next(q for q in stats["daily_quests"] if q["id"] == "daily_correct_3")
    assert quest["completed"] and quest["progress"] == 3

    # 追加で正解してもクエスト報酬は再付与されない
    extra = await _answer(auth_client, [q.id for q in html.questions if q.type == "choice"][3])
    assert "daily_correct_3" not in [q["id"] for q in extra["reward"]["completed_quests"]]


async def test_level_up_flag(auth_client: AsyncClient) -> None:
    html = get_catalog().get_course("course-html-css")
    leveled = False
    for q in html.questions:
        res = await _answer(auth_client, q.id)
        leveled = leveled or res["reward"]["leveled_up"]
    assert leveled  # 9 問 + クエストで 50 XP (L2) を超える
    stats = (await auth_client.get(f"{API}/gamification/me")).json()
    assert stats["level"] >= 2
    assert stats["level"] == g.level_for_xp(stats["total_xp"])


async def test_gamification_me_defaults(auth_client: AsyncClient) -> None:
    stats = (await auth_client.get(f"{API}/gamification/me")).json()
    assert stats["total_xp"] == 0 and stats["level"] == 1 and stats["current_streak"] == 0
    assert len(stats["daily_quests"]) == len(g.DAILY_QUESTS)


async def test_streak_across_days(auth_client: AsyncClient, session_factory) -> None:
    me = await auth_client.get(f"{API}/gamification/me")
    assert me.status_code == 200
    # ゲストユーザーの ID を取得するため 1 問回答してから台帳を直接操作する
    await _answer(auth_client, "q-html-heading")
    async with session_factory() as session:
        from sqlalchemy import select

        from app.models import UserStats

        user_id = (await session.execute(select(UserStats.user_id))).scalar_one()
        service = GamificationService(GamificationRepository(session))
        today = g.local_today()
        for offset, key in ((1, "a"), (2, "b")):
            await service.award(
                str(user_id), amount=1, reason="test", key=key, today=today + timedelta(days=offset)
            )
        await session.commit()
        stats = await service.get_stats(str(user_id), today + timedelta(days=2))
        assert stats.current_streak == 3 and stats.longest_streak == 3
        # 2 日空くと途切れる
        stats = await service.get_stats(str(user_id), today + timedelta(days=4))
        assert stats.current_streak == 0 and stats.longest_streak == 3


async def test_lesson_submit_awards_xp(auth_client: AsyncClient, session_factory) -> None:
    from app.models import Course, CourseLevel, Difficulty, Lesson, LessonType

    async with session_factory() as session:
        course = Course(title="c", level=CourseLevel.beginner, is_published=True)
        session.add(course)
        await session.flush()
        lesson = Lesson(
            course_id=course.id,
            title="l",
            lesson_type=LessonType.quiz,
            difficulty=Difficulty.easy,
            content={"question": "?", "choices": ["a", "b"], "correct_index": 1},
            tags=["t"],
            is_published=True,
        )
        session.add(lesson)
        await session.commit()
        lesson_id = str(lesson.id)

    for _ in range(2):
        res = await auth_client.post(
            f"{API}/courses/lessons/{lesson_id}/submit", json={"answer": {"selected_index": 1}}
        )
        assert res.status_code == 200, res.text
    stats = (await auth_client.get(f"{API}/gamification/me")).json()
    assert stats["total_xp"] == g.LESSON_FIRST_CORRECT_XP
