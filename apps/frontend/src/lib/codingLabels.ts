import type {
  CodingDifficulty,
  CodingQuestionType,
  Framework,
  IssueStatus,
  Language,
  MonacoLanguage,
} from "@/types/coding";

/** 言語・フレームワーク・難易度などの表示ラベル */
export const LANGUAGE_LABEL: Record<Language, string> = {
  javascript: "JavaScript",
  typescript: "TypeScript",
  python: "Python",
  sql: "SQL",
  html: "HTML",
  css: "CSS",
  go: "Go",
  java: "Java",
};

export const LANGUAGE_ICON: Record<Language, string> = {
  javascript: "⚡",
  typescript: "🔷",
  python: "🐍",
  sql: "🗄️",
  html: "🎨",
  css: "💅",
  go: "🐹",
  java: "☕",
};

export const FRAMEWORK_LABEL: Record<Framework, string> = {
  react: "React",
  next: "Next.js",
  vue: "Vue",
  nuxt: "Nuxt",
  node: "Node.js",
  express: "Express",
  nestjs: "NestJS",
  fastapi: "FastAPI",
  django: "Django",
  flask: "Flask",
  postgres: "PostgreSQL",
  mysql: "MySQL",
  sqlite: "SQLite",
  tailwind: "Tailwind CSS",
  "css-modules": "CSS Modules",
  sass: "Sass",
  gin: "Gin",
  echo: "Echo",
  "spring-boot": "Spring Boot",
};

export const LANGUAGE_MONACO: Record<Language, MonacoLanguage> = {
  javascript: "javascript",
  typescript: "typescript",
  python: "python",
  sql: "sql",
  html: "html",
  css: "css",
  go: "go",
  java: "java",
};

export const DIFFICULTY_LABEL: Record<CodingDifficulty, string> = {
  easy: "初級",
  normal: "中級",
  hard: "上級",
};

export const ISSUE_STATUS_LABEL: Record<IssueStatus, string> = {
  open: "Open",
  "in-progress": "In Progress",
  solved: "Solved",
};

export const QUESTION_TYPE_LABEL: Record<CodingQuestionType, string> = {
  "fill-blank": "穴埋め",
  implementation: "実装",
  refactor: "リファクタ",
  bugfix: "バグ修正",
};

export function languageLabel(language: string): string {
  return LANGUAGE_LABEL[language as Language] ?? language;
}

export function languageIcon(language: string): string {
  return LANGUAGE_ICON[language as Language] ?? "📄";
}

export function frameworkLabel(framework: string): string {
  return FRAMEWORK_LABEL[framework as Framework] ?? framework;
}

export function questionTypeLabel(type: string): string {
  return QUESTION_TYPE_LABEL[type as CodingQuestionType] ?? type;
}
