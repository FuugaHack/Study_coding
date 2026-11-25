from fastapi import APIRouter, Depends

from app.core.security import get_current_user_id
from app.dependencies import get_gamification_service
from app.schemas.gamification import GamificationStatsResponse
from app.services.gamification_service import GamificationService

router = APIRouter(prefix="/gamification", tags=["gamification"])


@router.get("/me", response_model=GamificationStatsResponse)
async def get_my_stats(
    user_id: str = Depends(get_current_user_id),
    service: GamificationService = Depends(get_gamification_service),
):
    return await service.get_stats(user_id)
