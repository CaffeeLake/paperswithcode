import type { AuthUser } from "./authContext";

export function paperEditSubmitMode(
  user: AuthUser | null,
): "direct" | "pending" {
  return user?.can_directly_edit_catalog ? "direct" : "pending";
}
