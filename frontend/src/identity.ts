export interface SavedLeagueIdentity {
  username: string | null;
  leagueId: string | null;
  rosterId: string | null;
}

export function getCookie(name: string): string | null {
  const key = `${name}=`;
  const row = document.cookie.split('; ').find((item) => item.startsWith(key));
  return row ? decodeURIComponent(row.slice(key.length)) : null;
}

export function setCookie(name: string, value: string, days = 365): void {
  // biome-ignore lint/suspicious/noDocumentCookie: the existing API contract reads these browser cookies synchronously.
  document.cookie = `${name}=${encodeURIComponent(value)}; max-age=${days * 86400}; path=/; SameSite=Lax`;
}

export function currentNflSeason(): string {
  const now = new Date();
  return String(now.getUTCMonth() + 1 >= 3 ? now.getUTCFullYear() : now.getUTCFullYear() - 1);
}

export function savedLeagueIdentity(): SavedLeagueIdentity {
  return {
    username: getCookie('sleeper_username'),
    leagueId: getCookie('league_id'),
    rosterId: getCookie('roster_id'),
  };
}

export function hasSavedLeagueIdentity(): boolean {
  const identity = savedLeagueIdentity();
  return Boolean(identity.leagueId && identity.rosterId);
}

export function saveLeagueIdentity(username: string, leagueId: string, rosterId: string): void {
  setCookie('sleeper_username', username);
  setCookie('league_id', leagueId);
  setCookie('roster_id', rosterId);
}
