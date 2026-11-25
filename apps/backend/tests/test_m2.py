"""M2: バッジ / ウィークリークエスト / ストリークフリーズ / 実力テスト / ボス戦。"""
import random
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.content.loader import get_catalog
from app.domain import challenge as ch
from app.domain import gamification as g
from app.models import ChallengeSession, UserStats
from app.repositories.gamification_repository import GamificationRepository
from app.services.gamification_service import GamificationService
from tests.test_catalog_api import API, _answer, _correct_payload

TODAY = date(2026, 11, 25)  # 水曜日

# ================================================================ domain


def test_missed_days() -> None:
    assert g.missed_days(None, TODAY) == 0
    assert g.missed_days(TODAY, TODAY) == 0
    assert g.missed_days(TODAY - timedelta(days=1), TODAY) == 0
    assert g.missed_days(TODAY - timedelta(days=3), TODAY) == 2


def test_streak_freeze_protects_streak() -> None:
    state = g.StreakState(10, 10, TODAY - timedelta(days=3))  # 2 日休み
    assert g.advance_streak(state, TODAY, freezes=1).current == 1
    assert g.freezes_to_consume(state, TODAY, 1) == 0
    assert g.advance_streak(state, TODAY, freezes=2).current == 11
    assert g.freezes_to_consume(state, TODAY, 2) == 2
    assert g.effective_streak(state, TODAY, freezes=2) == 10
    assert g.effective_streak(state, TODAY, freezes=1) == 0


def test_week_start_is_monday() -> None:
    assert g.week_start(TODAY) == date(2026, 11, 23)
    assert g.week_start(date(2026, 11, 23)) == date(2026, 11, 23)


def test_quest_period_keys_differ() -> None:
    weekly = g.WEEKLY_QUESTS[0]
    assert weekly.period_start(TODAY) == date(2026, 11, 23)
    assert g.DAILY_QUESTS[0].period_start(TODAY) == TODAY


def test_newly_earned_badges() -> None:
    metrics = g.BadgeMetrics(solved_questions=12, current_streak=3, level=2)
    ids = {b.id for b in g.newly_earned_badges(metrics, owned={"first_step"})}
    assert ids == {"solver_10", "streak_3"}


def test_badge_ids_unique() -> None:
    assert len({b.id for b in g.BADGES}) == len(g.BADGES)


def test_challenge_score_threshold() -> None:
    assert ch.ChallengeScore(4, 5).passed
    assert not ch.ChallengeScore(3, 5).passed
    assert not ch.ChallengeScore(0, 0).passed
    assert ch.ChallengeScore(2, 3).percent == 67


def test_select_questions_excludes_text() -> None:
    course = get_catalog().get_course("course-javascript")
    picked = ch.select_questions(course, "boss", random.Random(1))
    assert picked and all(q.type != "text" for q in picked)
    assert len(picked) == min(ch.QUESTION_COUNT["boss"], len(ch.gradeable_questions(course)))


def test_ancestors() -> None:
    assert ch.ancestors(get_catalog(), "course-react") == {"course-typescript", "course-javascript"}
    assert ch.ancestors(get_catalog(), "course-javascript") == set()


# ================================================================ helpers


async def _user_id(session_factory) -> str:
    async with session_factory() as s:
        return str((await s.execute(select(UserStats.user_id))).scalar_one())


async def _start(client: AsyncClient, course_id: str, mode: str):
    return await client.post(f"{API}/challenges", json={"course_id": course_id, "mode": mode})


async def _submit_all_correct(client: AsyncClient, challenge: dict) -> dict:
    answers = {q["id"]: _correct_payload(q["id"]) for q in challenge["questions"]}
    res = await client.post(f"{API}/challenges/{challenge['id']}/submit", json={"answers": answers})
    assert res.status_code == 200, res.text
    return res.json()


async def _courses(client: AsyncClient) -> dict:
    body = (await client.get(f"{API}/catalog/courses")).json()
    return {c["id"]: c for c in body["courses"]}


# ================================================================ badges / shop


async def test_first_correct_earns_badge(auth_client: AsyncClient) -> None:
    res = await _answer(auth_client, "q-html-heading")
    assert [b["id"] for b in res["reward"]["new_badges"]] == ["first_step"]
    assert res["reward"]["coins_gained"] == g.BADGE_COINS

    badges = (await auth_client.get(f"{API}/gamification/badges")).json()["badges"]
    earned = {b["id"] for b in badges if b["earned_at"]}
    assert earned == {"first_step"}
    assert len(badges) == len(g.BADGES)

    again = await _answer(auth_client, "q-html-heading")
    assert again["reward"]["new_badges"] == []


async def test_shop_streak_freeze(auth_client: AsyncClient, session_factory) -> None:
    res = await auth_client.post(f"{API}/gamification/shop/streak-freeze")
    assert res.status_code == 409  # コイン不足 (user_stats もまだ無い)

    await _answer(auth_client, "q-html-heading")
    user_id = await _user_id(session_factory)
    async with session_factory() as s:
        await s.execute(update(UserStats).values(coins=200))
        await s.commit()

    for expected in (1, 2):
        res = await auth_client.post(f"{API}/gamification/shop/streak-freeze")
        assert res.status_code == 200, res.text
        assert res.json()["streak_freezes"] == expected
    assert res.json()["coins"] == 200 - 2 * g.STREAK_FREEZE_COST
    res = await auth_client.post(f"{API}/gamification/shop/streak-freeze")
    assert res.status_code == 409  # 上限

    async with session_factory() as s:
        service = GamificationService(GamificationRepository(s), get_catalog())
        stats = await service.get_stats(user_id)
        assert stats.streak_freezes == 2


async def test_freeze_is_consumed_when_returning(auth_client: AsyncClient, session_factory) -> None:
    await _answer(auth_client, "q-html-heading")
    today = g.local_today()
    async with session_factory() as s:
        await s.execute(
            update(UserStats).values(
                current_streak=5,
                longest_streak=5,
                last_active_date=today - timedelta(days=2),
                streak_freezes=1,
            )
        )
        await s.commit()

    me = (await auth_client.get(f"{API}/gamification/me")).json()
    assert me["current_streak"] == 5  # フリーズで守られている

    res = await _answer(auth_client, "q-html-link")
    assert res["stats"]["current_streak"] == 6
    assert res["stats"]["streak_freezes"] == 0


async def test_weekly_quests_listed(auth_client: AsyncClient) -> None:
    me = (await auth_client.get(f"{API}/gamification/me")).json()
    assert [q["id"] for q in me["weekly_quests"]] == [q.id for q in g.WEEKLY_QUESTS]


# ================================================================ placement


async def test_placement_skips_locked_course(auth_client: AsyncClient) -> None:
    courses = await _courses(auth_client)
    assert courses["course-typescript"]["is_locked"]
    assert courses["course-typescript"]["can_take_placement"]

    res = await _start(auth_client, "course-typescript", "placement")
    assert res.status_code == 201, res.text
    challenge = res.json()
    assert challenge["questions"] and "answer" not in str(challenge["questions"])
    assert challenge["time_limit_seconds"] > 0

    result = await _submit_all_correct(auth_client, challenge)
    assert result["passed"] and result["percent"] == 100
    assert result["reward"]["xp_gained"] >= ch.PLACEMENT_XP
    assert "placement_1" in [b["id"] for b in result["reward"]["new_badges"]]
    assert "React 入門" in result["unlocked_courses"]

    courses = await _courses(auth_client)
    assert courses["course-typescript"]["skipped"] and courses["course-typescript"]["is_cleared"]
    assert courses["course-javascript"]["is_cleared"]  # 前提コースもクリア扱い
    assert not courses["course-react"]["is_locked"]
    assert not courses["course-typescript"]["can_take_placement"]


async def test_placement_once_per_day_and_not_when_cleared(auth_client: AsyncClient) -> None:
    first = await _start(auth_client, "course-sql", "placement")
    assert first.status_code == 201
    wrong = {q["id"]: {"selected": "__wrong__"} for q in first.json()["questions"]}
    res = await auth_client.post(
        f"{API}/challenges/{first.json()['id']}/submit", json={"answers": wrong}
    )
    assert res.status_code == 200 and not res.json()["passed"]
    assert res.json()["reward"]["xp_gained"] == 0

    assert (await _start(auth_client, "course-sql", "placement")).status_code == 409

    # 合格済み (クリア済み) のコースは受験できない
    ok = await _start(auth_client, "course-python", "placement")
    await _submit_all_correct(auth_client, ok.json())
    courses = await _courses(auth_client)
    assert courses["course-python"]["is_cleared"]


async def test_challenge_unavailable_for_tiny_course(auth_client: AsyncClient) -> None:
    courses = await _courses(auth_client)
    tiny = next(cid for cid, c in courses.items() if not c["can_take_placement"] and c["is_locked"])
    assert (await _start(auth_client, tiny, "placement")).status_code == 409


# ================================================================ boss


async def test_boss_requires_clear_then_rewards_once(auth_client: AsyncClient) -> None:
    assert (await _start(auth_client, "course-javascript", "boss")).status_code == 403

    js = get_catalog().get_course("course-javascript")
    for q in js.questions:
        await _answer(auth_client, q.id)
    assert (await _courses(auth_client))["course-javascript"]["can_challenge_boss"]

    lose = (await _start(auth_client, "course-javascript", "boss")).json()
    res = await auth_client.post(f"{API}/challenges/{lose['id']}/submit", json={"answers": {}})
    assert not res.json()["passed"] and res.json()["percent"] == 0
    assert all(r["correct_answer"] is None for r in res.json()["results"])

    win = (await _start(auth_client, "course-javascript", "boss")).json()
    result = await _submit_all_correct(auth_client, win)
    assert result["passed"]
    assert result["reward"]["xp_gained"] >= ch.BOSS_XP
    assert "boss_1" in [b["id"] for b in result["reward"]["new_badges"]]
    assert "weekly_boss_1" in [q["id"] for q in result["reward"]["completed_quests"]]
    assert (await _courses(auth_client))["course-javascript"]["boss_defeated"]

    again = await _submit_all_correct(
        auth_client, (await _start(auth_client, "course-javascript", "boss")).json()
    )
    assert again["passed"] and again["reward"]["xp_gained"] == 0  # 報酬は初回のみ
    assert (await _start(auth_client, "course-javascript", "boss")).status_code == 409  # 1 日 3 回


async def test_submit_twice_and_timeout(auth_client: AsyncClient, session_factory) -> None:
    challenge = (await _start(auth_client, "course-html-css", "placement")).json()
    async with session_factory() as s:
        await s.execute(
            update(ChallengeSession).values(expires_at=datetime.now(UTC) - timedelta(minutes=5))
        )
        await s.commit()

    result = await _submit_all_correct(auth_client, challenge)
    assert result["timed_out"] and not result["passed"]
    assert result["results"][0]["correct_answer"] is None  # 不合格では答えを見せない

    res = await auth_client.post(
        f"{API}/challenges/{challenge['id']}/submit", json={"answers": {}}
    )
    assert res.status_code == 409


@pytest.mark.parametrize("challenge_id", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
async def test_unknown_challenge_404(auth_client: AsyncClient, challenge_id: str) -> None:
    assert (await auth_client.get(f"{API}/challenges/{challenge_id}")).status_code == 404


async def test_challenge_belongs_to_user(auth_client: AsyncClient, client: AsyncClient) -> None:
    challenge = (await _start(auth_client, "course-html-css", "placement")).json()
    other = (await client.post(f"{API}/auth/guest")).json()["access_token"]
    res = await client.get(
        f"{API}/challenges/{challenge['id']}", headers={"Authorization": f"Bearer {other}"}
    )
    assert res.status_code == 404


# ================================================================ review fixes


async def test_practice_blocked_during_open_challenge(auth_client: AsyncClient) -> None:
    challenge = (await _start(auth_client, "course-html-css", "placement")).json()
    qid = challenge["questions"][0]["id"]
    res = await auth_client.post(
        f"{API}/catalog/questions/{qid}/answer", json=_correct_payload(qid)
    )
    assert res.status_code == 409

    await auth_client.post(f"{API}/challenges/{challenge['id']}/submit", json={"answers": {}})
    assert (await _answer(auth_client, qid))["result"] == "correct"


async def test_answers_revealed_by_passed_challenge_give_review_xp(
    auth_client: AsyncClient,
) -> None:
    challenge = (await _start(auth_client, "course-javascript", "placement")).json()
    answers = {q["id"]: _correct_payload(q["id"]) for q in challenge["questions"]}
    missed = challenge["questions"][0]["id"]
    del answers[missed]  # 1 問だけ空欄 (5 問中 4 問正解 = 80% で合格)
    res = await auth_client.post(
        f"{API}/challenges/{challenge['id']}/submit", json={"answers": answers}
    )
    body = res.json()
    assert body["passed"]
    assert next(r for r in body["results"] if r["question_id"] == missed)["correct_answer"]

    later = await _answer(auth_client, missed)
    assert later["result"] == "correct"
    quest_xp = sum(q["reward_xp"] for q in later["reward"]["completed_quests"])
    assert later["reward"]["xp_gained"] - quest_xp == g.REVIEW_XP


async def test_cannot_buy_freeze_after_missing_days(
    auth_client: AsyncClient, session_factory
) -> None:
    await _answer(auth_client, "q-html-heading")
    async with session_factory() as s:
        await s.execute(
            update(UserStats).values(
                coins=200, last_active_date=g.local_today() - timedelta(days=3)
            )
        )
        await s.commit()
    res = await auth_client.post(f"{API}/gamification/shop/streak-freeze")
    assert res.status_code == 409


async def test_challenge_response_has_server_time(auth_client: AsyncClient) -> None:
    challenge = (await _start(auth_client, "course-html-css", "placement")).json()
    assert challenge["server_now"] < challenge["expires_at"]
