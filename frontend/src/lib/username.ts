// Username validation. The backend treats the username as an opaque
// 3-32 char lowercase string ([a-z0-9_]); mirror that here so the
// client can fail fast in <UsernamePrompt />.

const USERNAME_PATTERN = /^[a-z0-9_]{3,32}$/;

export function isValidBackendUsername(value: string): boolean {
  return USERNAME_PATTERN.test(value.toLowerCase().trim());
}
