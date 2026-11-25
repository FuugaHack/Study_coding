// UI で使うカタログ型 (API レスポンスを src/api/catalog.ts で変換したもの)

export type CourseLevel = "beginner" | "intermediate" | "advanced";

export type CourseCategory =
  | "frontend"
  | "backend"
  | "ai"
  | "database"
  | "infra"
  | "testing"
  | "practice";

export type CourseStatus = "not-started" | "in-progress" | "completed" | "locked";

export type QuestionType = "choice" | "multiple-choice" | "text" | "code";

export type QuestionDifficulty = "easy" | "normal" | "hard";

/** 正解・解説はサーバーが回答後にのみ返す (クライアントには同梱しない) */
export type Question = {
  id: string;
  type: QuestionType;
  title: string;
  description: string;
  choices: string[];
  difficulty: QuestionDifficulty;
  /** code 型のみ: `___` の箇所が穴埋め対象 */
  codeTemplate: string;
  blankCount: number;
  solved: boolean;
};

export type Course = {
  id: string;
  title: string;
  description: string;
  category: CourseCategory;
  level: CourseLevel;
  status: CourseStatus;
  icon: string;
  estimatedHours: number;
  questionCount: number;
  solvedCount: number;
  /** 0〜100 */
  progress: number;
  isLocked: boolean;
  tags: string[];
  /** 解放に必要なコースのタイトル */
  prerequisiteTitles: string[];
};

export type CourseDetail = Course & { questions: Question[] };

export type CourseCatalogResponse = {
  courses: Course[];
};
