import type { WeekWindow } from '../state/workspace';
import type { PlayerOddsDetails, ProjectionResponse } from '../types';

function getCookie(name: string): string | null {
  const key = `${name}=`;
  const row = document.cookie.split('; ').find((item) => item.startsWith(key));
  return row ? decodeURIComponent(row.slice(key.length)) : null;
}

function currentNflSeason(): string {
  const now = new Date();
  return String(now.getUTCMonth() + 1 >= 3 ? now.getUTCFullYear() : now.getUTCFullYear() - 1);
}

function identityParams(): URLSearchParams | null {
  const params = new URLSearchParams();
  const leagueId = getCookie('league_id');
  const rosterId = getCookie('roster_id');

  if (leagueId && rosterId) {
    params.set('league_id', leagueId);
    params.set('roster_id', rosterId);
    return params;
  }

  const username = getCookie('sleeper_username');
  if (!username) return null;
  params.set('username', username);
  params.set('season', currentNflSeason());
  return params;
}

function requestInit(signal?: AbortSignal): RequestInit {
  const request: RequestInit = { headers: { Accept: 'application/json' } };
  if (signal) request.signal = signal;
  return request;
}

async function fetchJson<T extends { error?: string }>(
  path: string,
  params: URLSearchParams,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${path}?${params.toString()}`, requestInit(signal));
  const payload = (await response.json()) as T;
  if (!response.ok) {
    throw new Error(payload.error || `Request failed (${response.status}).`);
  }
  return payload;
}

export class MissingIdentityError extends Error {
  constructor() {
    super('No saved Sleeper league identity was found.');
    this.name = 'MissingIdentityError';
  }
}

export async function fetchProjections(
  week: WeekWindow,
  signal?: AbortSignal,
): Promise<ProjectionResponse> {
  const params = identityParams();
  if (!params) throw new MissingIdentityError();
  params.set('week', week);
  params.set('mode', 'auto');
  return fetchJson<ProjectionResponse>('/projections', params, signal);
}

export async function fetchPlayerDetails(
  name: string,
  week: WeekWindow,
  signal?: AbortSignal,
): Promise<PlayerOddsDetails> {
  const params = identityParams();
  if (!params) throw new MissingIdentityError();
  params.set('name', name);
  params.set('week', week);
  params.set('mode', 'auto');
  return fetchJson<PlayerOddsDetails>('/player/odds', params, signal);
}
