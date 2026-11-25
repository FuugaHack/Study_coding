// backend: app/schemas/coding.py と対応
import type { GamificationStatsResponse, RewardResponse } from "./gamification";

export type CodingIssueStatus = "open" | "in-progress" | "solved";
export type CodingTestStatus = "passed" | "failed" | "error" | "timeout";

export interface CodingRepositorySummary {
  id: string;
  name: string;
  description: string;
  language: string;
  framework: string | null;
  tags: string[];
  difficulty_range: string;
  status: string;
  question_count: number;
  executable_count: number;
  solved_count: number;
}

export interface CodingRepositoryListResponse {
  repositories: CodingRepositorySummary[];
}

export interface CodingIssueSummary {
  id: string;
  repository_id: string;
  issue_number: number;
  title: string;
  description: string;
  language: string;
  framework: string | null;
  difficulty: "easy" | "normal" | "hard";
  type: string;
  estimated_minutes: number;
  tags: string[];
  /** サンドボックスで自動実行・採点できるか */
  executable: boolean;
  status: CodingIssueStatus;
}

export interface CodingIssueListResponse {
  repository: CodingRepositorySummary;
  issues: CodingIssueSummary[];
}

export interface CodingHint {
  level: number;
  title: string;
  content: string;
  closeness: string;
}

export interface CodingIssueDetail extends CodingIssueSummary {
  initial_code: string;
  explanation: string;
  visible_tests: { name: string; stdin: string; expected: string }[];
  hidden_test_count: number;
  /** 開いたヒントのみ */
  hints: CodingHint[];
  hints_total: number;
  can_view_solutions: boolean;
}

export interface CodingTestResult {
  name: string;
  hidden: boolean;
  status: CodingTestStatus;
  /** 非公開テストでは null */
  stdin: string | null;
  expected: string | null;
  stdout: string | null;
  stderr: string | null;
  time_ms: number;
}

export interface CodingRunResponse {
  results: CodingTestResult[];
}

export interface CodingSubmitResponse {
  submission_id: string;
  /** 自動テスト非対応の問題は null */
  passed: boolean | null;
  passed_count: number;
  total_count: number;
  results: CodingTestResult[];
  reward: RewardResponse;
  stats: GamificationStatsResponse;
}

export interface CodingSolution {
  id: string;
  title: string;
  code: string;
  explanation: string;
  points: string[];
  is_recommended: boolean;
}

export interface CodingSolutionsResponse {
  solutions: CodingSolution[];
}

export interface CodeReviewAspect {
  score: number;
  comment: string;
}

export interface CodeReview {
  summary: string;
  aspects: Record<string, CodeReviewAspect>;
  good_points: string[];
  improvements: { title: string; detail: string; code_example: string | null }[];
  next_topics: string[];
}

/** AI レビューはワーカーで処理する。completed になるまでポーリングする */
export type CodingReviewStatus =
  | "not_requested"
  | "pending"
  | "processing"
  | "completed"
  | "failed";

export interface CodingReviewResponse {
  submission_id: string;
  status: CodingReviewStatus;
  passed: boolean | null;
  review: CodeReview | null;
  reviewed_at: string | null;
  error_message: string | null;
  aspect_labels: Record<string, string>;
}
