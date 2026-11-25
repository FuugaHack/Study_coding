from app.core.exceptions import NotFoundError
from app.repositories.problem_repository import ProblemRepository
from app.services.ai_usage import check_budget
from app.worker import queue

TASK_TYPE = "ai_review"

REVIEW_SYSTEM_PROMPT = """あなたはプログラミング教育の専門家です。
学習者のレベル: {level}

以下の観点でコードレビューしてください:
1. 正確性: コードが問題の要件を満たしているか
2. 効率性: 時間・空間計算量は適切か
3. 可読性: 変数名、構造は適切か
4. ベストプラクティス: {language}の慣習に沿っているか
5. 改善点: 具体的な改善案（コード例付き）

学習者のレベルに合わせた説明をしてください。
- beginner: 基本的な概念から丁寧に
- intermediate: ポイントを絞って
- advanced: 高度な最適化やデザインパターンにも言及"""


class AIReviewService:
    def __init__(self, problem_repo: ProblemRepository):
        self.problem_repo = problem_repo

    async def request_review(
        self,
        user_id: str,
        code: str,
        problem_description: str,
        language: str = "python",
        user_level: str = "beginner",
    ) -> str:
        """レビューをワーカーに登録し、task_id を返す (LLM はここでは呼ばない)。"""
        await check_budget(self.problem_repo.db, user_id)
        task = await queue.enqueue(
            self.problem_repo.db,
            task_type=TASK_TYPE,
            user_id=user_id,
            input_data={
                "code": code,
                "problem_description": problem_description,
                "language": language,
                "user_level": user_level,
            },
        )
        # レスポンスより前にコミットする (直後のポーリングで 404 にならないように)
        await self.problem_repo.db.commit()
        return str(task.id)

    async def get_review_result(self, task_id: str, user_id: str) -> dict:
        task = await self.problem_repo.get_async_task(task_id, user_id)
        if not task:
            raise NotFoundError("タスク")

        result = {
            "task_id": str(task.id),
            "status": task.status.value,
        }
        if task.result_data:
            result["review"] = task.result_data.get("review")
        if task.error_message:
            result["error_message"] = task.error_message

        return result


async def run_ai_review_task(ctx) -> dict:
    """自由入力コードの AI レビュー (ワーカーで実行)。"""
    data = ctx.task.input_data
    language = data.get("language", "python")
    system_prompt = REVIEW_SYSTEM_PROMPT.format(
        level=data.get("user_level", "beginner"), language=language
    )
    user_message = f"""## 問題
{data.get("problem_description", "")}

## 提出コード ({language})
```{language}
{data.get("code", "")}
```"""
    response = await ctx.complete(TASK_TYPE, system_prompt, user_message)
    return {"review": response.text}
