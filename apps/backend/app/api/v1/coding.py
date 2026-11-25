from fastapi import APIRouter, Depends

from app.core.rate_limit import rate_limit_ai, rate_limit_runner, runner_slot
from app.core.security import get_current_user_id
from app.dependencies import get_coding_service
from app.schemas.coding import (
    CodeRequest,
    CodingIssueDetail,
    CodingIssueListResponse,
    CodingRepositoryListResponse,
    DisputeRequest,
    HintResponse,
    ReviewResponse,
    RunResponse,
    SolutionsResponse,
    SubmitResponse,
)
from app.services.coding_service import CodingService

router = APIRouter(prefix="/coding", tags=["coding"])


@router.get("/repositories", response_model=CodingRepositoryListResponse)
async def list_repositories(
    user_id: str = Depends(get_current_user_id),
    service: CodingService = Depends(get_coding_service),
):
    return await service.list_repositories(user_id)


@router.get("/repositories/{repository_id}/issues", response_model=CodingIssueListResponse)
async def list_issues(
    repository_id: str,
    user_id: str = Depends(get_current_user_id),
    service: CodingService = Depends(get_coding_service),
):
    return await service.list_issues(user_id, repository_id)


@router.get("/issues/{question_id}", response_model=CodingIssueDetail)
async def get_issue(
    question_id: str,
    user_id: str = Depends(get_current_user_id),
    service: CodingService = Depends(get_coding_service),
):
    return await service.get_issue(user_id, question_id)


@router.post("/issues/{question_id}/hints", response_model=list[HintResponse])
async def reveal_hint(
    question_id: str,
    user_id: str = Depends(get_current_user_id),
    service: CodingService = Depends(get_coding_service),
):
    return await service.reveal_hint(user_id, question_id)


@router.post("/issues/{question_id}/solutions", response_model=SolutionsResponse)
async def view_solutions(
    question_id: str,
    user_id: str = Depends(get_current_user_id),
    service: CodingService = Depends(get_coding_service),
):
    return await service.view_solutions(user_id, question_id)


@router.post("/issues/{question_id}/run", response_model=RunResponse)
async def run_code(
    question_id: str,
    req: CodeRequest,
    user_id: str = Depends(get_current_user_id),
    service: CodingService = Depends(get_coding_service),
):
    await rate_limit_runner(user_id)
    async with runner_slot(user_id):
        return await service.run(user_id, question_id, req.code)


@router.post("/issues/{question_id}/submit", response_model=SubmitResponse)
async def submit_code(
    question_id: str,
    req: CodeRequest,
    user_id: str = Depends(get_current_user_id),
    service: CodingService = Depends(get_coding_service),
):
    await rate_limit_runner(user_id)
    async with runner_slot(user_id):
        return await service.submit(user_id, question_id, req.code)


@router.post("/submissions/{submission_id}/review", response_model=ReviewResponse, status_code=202)
async def request_review(
    submission_id: str,
    user_id: str = Depends(get_current_user_id),
    service: CodingService = Depends(get_coding_service),
):
    """AI レビューを登録する。結果は GET で取得する (ワーカーで処理)。"""
    await rate_limit_ai(user_id)
    return await service.request_review(user_id, submission_id)


@router.get("/submissions/{submission_id}/review", response_model=ReviewResponse)
async def get_review(
    submission_id: str,
    user_id: str = Depends(get_current_user_id),
    service: CodingService = Depends(get_coding_service),
):
    return await service.get_review(user_id, submission_id)


@router.post("/submissions/{submission_id}/dispute", status_code=204)
async def dispute_review(
    submission_id: str,
    req: DisputeRequest,
    user_id: str = Depends(get_current_user_id),
    service: CodingService = Depends(get_coding_service),
):
    await service.dispute(user_id, submission_id, req.reason)
