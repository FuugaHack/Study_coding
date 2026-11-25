import type {
  AnswerRequest,
  AnswerResponse,
  CatalogCourseDetailResponse,
  CatalogCourseListResponse,
  CatalogCourseSummary,
  CatalogQuestion,
} from "@learning-platform/shared-types";
import { api } from "@/lib/api";
import type {
  Course,
  CourseCatalogResponse,
  CourseCategory,
  CourseDetail,
  CourseLevel,
  Question,
} from "@/types/catalog";

function toCourse(c: CatalogCourseSummary): Course {
  return {
    id: c.id,
    title: c.title,
    description: c.description,
    category: c.category as CourseCategory,
    level: c.level as CourseLevel,
    status: c.status,
    icon: c.icon,
    estimatedHours: c.estimated_hours,
    questionCount: c.question_count,
    solvedCount: c.solved_count,
    progress: c.progress,
    isLocked: c.is_locked,
    tags: c.tags,
    prerequisiteTitles: c.prerequisite_titles,
  };
}

function toQuestion(q: CatalogQuestion): Question {
  return {
    id: q.id,
    type: q.type,
    title: q.title,
    description: q.description,
    choices: q.choices ?? [],
    difficulty: q.difficulty,
    codeTemplate: q.code_template ?? "",
    blankCount: q.blank_count ?? 0,
    solved: q.solved,
  };
}

export async function fetchCourseCatalog(): Promise<CourseCatalogResponse> {
  const { data } = await api.get<CatalogCourseListResponse>("/catalog/courses");
  return { courses: data.courses.map(toCourse) };
}

export async function fetchCatalogCourse(courseId: string): Promise<CourseDetail> {
  const { data } = await api.get<CatalogCourseDetailResponse>(
    `/catalog/courses/${encodeURIComponent(courseId)}`,
  );
  return { ...toCourse(data), questions: data.questions.map(toQuestion) };
}

export async function answerQuestion(questionId: string, body: AnswerRequest) {
  const { data } = await api.post<AnswerResponse>(
    `/catalog/questions/${encodeURIComponent(questionId)}/answer`,
    body,
  );
  return data;
}
