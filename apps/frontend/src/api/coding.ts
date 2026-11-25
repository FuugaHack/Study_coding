import type {
  CodingHint,
  CodingIssueDetail,
  CodingIssueListResponse,
  CodingRepositoryListResponse,
  CodingReviewResponse,
  CodingRunResponse,
  CodingSolutionsResponse,
  CodingSubmitResponse,
} from "@learning-platform/shared-types";
import { api } from "@/lib/api";

const enc = encodeURIComponent;

export async function listCodingRepositories() {
  const { data } = await api.get<CodingRepositoryListResponse>("/coding/repositories");
  return data;
}

export async function listCodingIssues(repositoryId: string) {
  const { data } = await api.get<CodingIssueListResponse>(
    `/coding/repositories/${enc(repositoryId)}/issues`,
  );
  return data;
}

export async function getCodingIssue(questionId: string) {
  const { data } = await api.get<CodingIssueDetail>(`/coding/issues/${enc(questionId)}`);
  return data;
}

export async function revealCodingHint(questionId: string) {
  const { data } = await api.post<CodingHint[]>(`/coding/issues/${enc(questionId)}/hints`);
  return data;
}

export async function viewCodingSolutions(questionId: string) {
  const { data } = await api.post<CodingSolutionsResponse>(
    `/coding/issues/${enc(questionId)}/solutions`,
  );
  return data;
}

export async function runCode(questionId: string, code: string) {
  const { data } = await api.post<CodingRunResponse>(`/coding/issues/${enc(questionId)}/run`, {
    code,
  });
  return data;
}

export async function submitCode(questionId: string, code: string) {
  const { data } = await api.post<CodingSubmitResponse>(
    `/coding/issues/${enc(questionId)}/submit`,
    { code },
  );
  return data;
}

export async function requestCodeReview(submissionId: string) {
  const { data } = await api.post<CodingReviewResponse>(
    `/coding/submissions/${enc(submissionId)}/review`,
  );
  return data;
}

export async function getCodeReview(submissionId: string) {
  const { data } = await api.get<CodingReviewResponse>(
    `/coding/submissions/${enc(submissionId)}/review`,
  );
  return data;
}

export async function disputeReview(submissionId: string, reason: string) {
  await api.post(`/coding/submissions/${enc(submissionId)}/dispute`, { reason });
}
