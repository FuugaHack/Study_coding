from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.coding import get_coding_catalog
from app.content.loader import get_catalog
from app.db.session import get_db
from app.repositories.attempt_repository import AttemptRepository
from app.repositories.coding_repository import CodingRepository
from app.repositories.course_repository import CourseRepository
from app.repositories.gamification_repository import GamificationRepository
from app.repositories.problem_repository import ProblemRepository
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.user_repository import UserRepository
from app.services.ai_review_service import AIReviewService
from app.services.auth_service import AuthService
from app.services.bedrock_service import BedrockService
from app.services.catalog_service import CatalogService
from app.services.challenge_service import ChallengeService
from app.services.coding_service import CodingService
from app.services.course_service import CourseService
from app.services.gamification_service import GamificationService
from app.services.history_service import HistoryService
from app.services.problem_generation_service import ProblemGenerationService
from app.services.recommendation_service import RecommendationService
from app.services.runner_client import RunnerClient

# --- Repositories ---


def get_user_repo(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_course_repo(db: AsyncSession = Depends(get_db)) -> CourseRepository:
    return CourseRepository(db)


def get_problem_repo(db: AsyncSession = Depends(get_db)) -> ProblemRepository:
    return ProblemRepository(db)


def get_attempt_repo(db: AsyncSession = Depends(get_db)) -> AttemptRepository:
    return AttemptRepository(db)


def get_recommendation_repo(db: AsyncSession = Depends(get_db)) -> RecommendationRepository:
    return RecommendationRepository(db)


def get_gamification_repo(db: AsyncSession = Depends(get_db)) -> GamificationRepository:
    return GamificationRepository(db)


# --- Services ---


def get_bedrock_service() -> BedrockService:
    return BedrockService()


def get_auth_service(user_repo: UserRepository = Depends(get_user_repo)) -> AuthService:
    return AuthService(user_repo)


def get_gamification_service(
    repo: GamificationRepository = Depends(get_gamification_repo),
) -> GamificationService:
    return GamificationService(repo, get_catalog())


def get_catalog_service(
    repo: GamificationRepository = Depends(get_gamification_repo),
    gamification: GamificationService = Depends(get_gamification_service),
) -> CatalogService:
    return CatalogService(get_catalog(), repo, gamification)


def get_challenge_service(
    repo: GamificationRepository = Depends(get_gamification_repo),
    gamification: GamificationService = Depends(get_gamification_service),
    catalog_service: CatalogService = Depends(get_catalog_service),
) -> ChallengeService:
    return ChallengeService(get_catalog(), repo, gamification, catalog_service)


def get_runner_client() -> RunnerClient:
    return RunnerClient()


def get_coding_service(
    db: AsyncSession = Depends(get_db),
    gamification: GamificationService = Depends(get_gamification_service),
    runner: RunnerClient = Depends(get_runner_client),
) -> CodingService:
    return CodingService(get_coding_catalog(), CodingRepository(db), gamification, runner)


def get_course_service(
    course_repo: CourseRepository = Depends(get_course_repo),
    attempt_repo: AttemptRepository = Depends(get_attempt_repo),
    gamification: GamificationService = Depends(get_gamification_service),
    runner: RunnerClient = Depends(get_runner_client),
) -> CourseService:
    return CourseService(course_repo, attempt_repo, gamification, runner)


def get_problem_generation_service(
    problem_repo: ProblemRepository = Depends(get_problem_repo),
) -> ProblemGenerationService:
    return ProblemGenerationService(problem_repo)


def get_ai_review_service(
    problem_repo: ProblemRepository = Depends(get_problem_repo),
) -> AIReviewService:
    return AIReviewService(problem_repo)


def get_history_service(
    attempt_repo: AttemptRepository = Depends(get_attempt_repo),
) -> HistoryService:
    return HistoryService(attempt_repo)


def get_recommendation_service(
    attempt_repo: AttemptRepository = Depends(get_attempt_repo),
    recommendation_repo: RecommendationRepository = Depends(get_recommendation_repo),
    bedrock: BedrockService = Depends(get_bedrock_service),
) -> RecommendationService:
    return RecommendationService(attempt_repo, recommendation_repo, bedrock)
