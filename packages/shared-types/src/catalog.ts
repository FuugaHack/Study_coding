// backend: app/schemas/catalog.py と対応
import type { GamificationStatsResponse, RewardResponse } from "./gamification";

export type CatalogCourseStatus = "locked" | "not-started" | "in-progress" | "completed";
export type CatalogQuestionType = "choice" | "multiple-choice" | "text" | "code";

export interface CatalogCourseSummary {
  id: string;
  title: string;
  description: string;
  category: string;
  level: string;
  icon: string;
  estimated_hours: number;
  tags: string[];
  prerequisites: string[];
  prerequisite_titles: string[];
  question_count: number;
  solved_count: number;
  progress: number;
  status: CatalogCourseStatus;
  is_locked: boolean;
}

export interface CatalogCourseListResponse {
  courses: CatalogCourseSummary[];
  content_version: string;
}

/** クライアントに渡る問題。正解・解説は含まれない (回答後のレスポンスで返る)。 */
export interface CatalogQuestion {
  id: string;
  type: CatalogQuestionType;
  title: string;
  description: string;
  difficulty: "easy" | "normal" | "hard";
  choices: string[] | null;
  code_template: string | null;
  blank_count: number | null;
  solved: boolean;
}

export interface CatalogCourseDetailResponse extends CatalogCourseSummary {
  questions: CatalogQuestion[];
}

export interface AnswerRequest {
  selected?: string | string[];
  blanks?: string[];
  text?: string;
  time_spent_seconds?: number;
}

export interface AnswerResponse {
  question_id: string;
  result: "correct" | "incorrect" | "self_check";
  blank_results: boolean[];
  correct_answer: string | string[] | null;
  explanation: string | null;
  reward: RewardResponse;
  stats: GamificationStatsResponse;
}
