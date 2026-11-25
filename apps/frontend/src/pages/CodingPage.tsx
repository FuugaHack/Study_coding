import { useState } from "react";
import type { CodingIssueSummary, CodingRepositorySummary } from "@learning-platform/shared-types";
import { RepositoryList } from "@/components/coding/RepositoryList";
import { IssueList } from "@/components/coding/IssueList";
import { Editor } from "@/components/coding/Editor";

type Mode =
  | { kind: "repos" }
  | { kind: "issues"; repository: CodingRepositorySummary }
  | { kind: "editor"; repository: CodingRepositorySummary; issue: CodingIssueSummary };

export function CodingPage() {
  const [mode, setMode] = useState<Mode>({ kind: "repos" });

  if (mode.kind === "repos") {
    return <RepositoryList onSelect={(repository) => setMode({ kind: "issues", repository })} />;
  }

  if (mode.kind === "issues") {
    return (
      <IssueList
        repository={mode.repository}
        onBack={() => setMode({ kind: "repos" })}
        onSelect={(issue) => setMode({ kind: "editor", repository: mode.repository, issue })}
      />
    );
  }

  return (
    <Editor
      key={mode.issue.id}
      questionId={mode.issue.id}
      onBack={() => setMode({ kind: "issues", repository: mode.repository })}
    />
  );
}
