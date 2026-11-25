import type {
  ChallengeMode,
  ChallengeResponse,
  ChallengeResultResponse,
  SubmitChallengeRequest,
} from "@learning-platform/shared-types";
import { api } from "@/lib/api";

export async function startChallenge(courseId: string, mode: ChallengeMode) {
  const { data } = await api.post<ChallengeResponse>("/challenges", {
    course_id: courseId,
    mode,
  });
  return data;
}

export async function getChallenge(challengeId: string) {
  const { data } = await api.get<ChallengeResponse>(
    `/challenges/${encodeURIComponent(challengeId)}`,
  );
  return data;
}

export async function submitChallenge(challengeId: string, body: SubmitChallengeRequest) {
  const { data } = await api.post<ChallengeResultResponse>(
    `/challenges/${encodeURIComponent(challengeId)}/submit`,
    body,
  );
  return data;
}
