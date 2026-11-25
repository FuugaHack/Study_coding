from fastapi import APIRouter, Depends

from app.core.security import get_current_user_id
from app.dependencies import get_gamification_service
from app.schemas.gamification import (
    BadgesResponse,
    GamificationStatsResponse,
    ShopPurchaseResponse,
)
from app.services.gamification_service import GamificationService

router = APIRouter(prefix="/gamification", tags=["gamification"])


@router.get("/me", response_model=GamificationStatsResponse)
async def get_my_stats(
    user_id: str = Depends(get_current_user_id),
    service: GamificationService = Depends(get_gamification_service),
):
    return await service.get_stats(user_id)


@router.get("/badges", response_model=BadgesResponse)
async def get_my_badges(
    user_id: str = Depends(get_current_user_id),
    service: GamificationService = Depends(get_gamification_service),
):
    return await service.get_badges(user_id)


@router.post("/shop/streak-freeze", response_model=ShopPurchaseResponse)
async def buy_streak_freeze(
    user_id: str = Depends(get_current_user_id),
    service: GamificationService = Depends(get_gamification_service),
):
    result = await service.buy_streak_freeze(user_id)
    await service.repo.db.commit()
    return result
