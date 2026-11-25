from fastapi import APIRouter, Depends

from app.core.security import get_current_user_id
from app.dependencies import get_challenge_service
from app.schemas.challenge import (
    ChallengeResponse,
    ChallengeResultResponse,
    StartChallengeRequest,
    SubmitChallengeRequest,
)
from app.services.challenge_service import ChallengeService

router = APIRouter(prefix="/challenges", tags=["challenges"])


@router.post("", response_model=ChallengeResponse, status_code=201)
async def start_challenge(
    req: StartChallengeRequest,
    user_id: str = Depends(get_current_user_id),
    service: ChallengeService = Depends(get_challenge_service),
):
    return await service.start(user_id, req)


@router.get("/{challenge_id}", response_model=ChallengeResponse)
async def get_challenge(
    challenge_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ChallengeService = Depends(get_challenge_service),
):
    return await service.get(user_id, challenge_id)


@router.post("/{challenge_id}/submit", response_model=ChallengeResultResponse)
async def submit_challenge(
    challenge_id: str,
    req: SubmitChallengeRequest,
    user_id: str = Depends(get_current_user_id),
    service: ChallengeService = Depends(get_challenge_service),
):
    return await service.submit(user_id, challenge_id, req)
