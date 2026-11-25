// backend: app/schemas/challenge.py と対応
import type { AnswerRequest, CatalogQuestion } from "./catalog";
import type { GamificationStatsResponse, RewardResponse } from "./gamification";

export type ChallengeMode = "placement" | "boss";

export interface ChallengeResponse {
  id: string;
  course_id: string;
  course_title: string;
  mode: ChallengeMode;
  status: "open" | "passed" | "failed";
  questions: CatalogQuestion[];
  time_limit_seconds: number;
  expires_at: string;
  pass_percent: number;
  /** クライアントの時計ずれ補正用 */
  server_now: string;
}

export interface SubmitChallengeRequest {
  answers: Record<string, AnswerRequest>;
}

export interface ChallengeQuestionResult {
  question_id: string;
  correct: boolean;
  blank_results: boolean[];
  /** 合格時のみ */
  correct_answer: string | string[] | null;
  explanation: string | null;
}

export interface ChallengeResultResponse {
  id: string;
  course_id: string;
  mode: ChallengeMode;
  passed: boolean;
  timed_out: boolean;
  correct: number;
  total: number;
  percent: number;
  results: ChallengeQuestionResult[];
  unlocked_courses: string[];
  reward: RewardResponse;
  stats: GamificationStatsResponse;
}
