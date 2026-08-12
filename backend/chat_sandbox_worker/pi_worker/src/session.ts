export function shouldResetSession(
  boundAgentSession: string | undefined,
  resume: string | null,
): boolean {
  return boundAgentSession !== undefined && boundAgentSession !== resume;
}
