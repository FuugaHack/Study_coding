from fastapi import APIRouter, Depends

from app.core.security import get_current_user_id
from app.dependencies import get_catalog_service
from app.schemas.catalog import (
    AnswerRequest,
    AnswerResponse,
    CatalogCourseDetailResponse,
    CatalogCourseListResponse,
)
from app.services.catalog_service import CatalogService

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/courses", response_model=CatalogCourseListResponse)
async def list_courses(
    user_id: str = Depends(get_current_user_id),
    service: CatalogService = Depends(get_catalog_service),
):
    return await service.list_courses(user_id)


@router.get("/courses/{course_id}", response_model=CatalogCourseDetailResponse)
async def get_course(
    course_id: str,
    user_id: str = Depends(get_current_user_id),
    service: CatalogService = Depends(get_catalog_service),
):
    return await service.get_course(user_id, course_id)


@router.post("/questions/{question_id}/answer", response_model=AnswerResponse)
async def answer_question(
    question_id: str,
    req: AnswerRequest,
    user_id: str = Depends(get_current_user_id),
    service: CatalogService = Depends(get_catalog_service),
):
    return await service.answer(user_id, question_id, req)
