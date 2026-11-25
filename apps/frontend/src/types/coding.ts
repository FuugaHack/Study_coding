/** コーディング機能 (Repository → Issue → Editor) の UI 用の型。
 *  データ本体の型は @learning-platform/shared-types の Coding* を使う。 */

export type Language =
  | "javascript"
  | "typescript"
  | "python"
  | "sql"
  | "html"
  | "css"
  | "go"
  | "java";

export type Framework =
  | "react"
  | "next"
  | "vue"
  | "nuxt"
  | "node"
  | "express"
  | "nestjs"
  | "fastapi"
  | "django"
  | "flask"
  | "postgres"
  | "mysql"
  | "sqlite"
  | "tailwind"
  | "css-modules"
  | "sass"
  | "gin"
  | "echo"
  | "spring-boot";

export type MonacoLanguage = Language;

export type CodingDifficulty = "easy" | "normal" | "hard";
export type CodingQuestionType = "fill-blank" | "implementation" | "refactor" | "bugfix";
export type IssueStatus = "open" | "in-progress" | "solved";

export type HintCloseness =
  | "concept"
  | "focus"
  | "implementation"
  | "near-answer"
  | "almost-answer";

export type CodeDiffLine = {
  type: "added" | "removed" | "unchanged";
  content: string;
  lineNumber?: number;
};
