"""task_type ごとのハンドラー。"""

from app.services.ai_review_service import TASK_TYPE as AI_REVIEW
from app.services.ai_review_service import run_ai_review_task
from app.services.coding_service import CODE_REVIEW_TASK, run_code_review_task
from app.services.problem_generation_service import (
    TASK_TYPE as PROBLEM_GENERATION,
)
from app.services.problem_generation_service import run_problem_generation_task
from app.services.question_review_service import TASK_TYPE as QUESTION_REVIEW
from app.services.question_review_service import run_question_review_task

HANDLERS = {
    CODE_REVIEW_TASK: run_code_review_task,
    AI_REVIEW: run_ai_review_task,
    PROBLEM_GENERATION: run_problem_generation_task,
    QUESTION_REVIEW: run_question_review_task,
}
