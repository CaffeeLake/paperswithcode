export function safeExternalHref(value: unknown): string | null {
  if (
    typeof value !== "string" ||
    value.length > 2048 ||
    Array.from(value).some((char) => char.charCodeAt(0) <= 32 || char.charCodeAt(0) === 127)
  ) {
    return null;
  }
  try {
    const parsed = new URL(value);
    if ((parsed.protocol !== "http:" && parsed.protocol !== "https:") || !parsed.hostname) {
      return null;
    }
    if (parsed.username || parsed.password) return null;
    return parsed.href;
  } catch {
    return null;
  }
}
