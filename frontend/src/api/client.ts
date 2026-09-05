import { currentNflSeason, savedLeagueIdentity } from '../identity';
import type { DataMode, LineupTarget, WeekWindow } from '../state/workspace';
import type {
  DefenseResponse,
  LeagueResolution,
  LineupResponse,
  PlayerOddsDetails,
  ProjectionResponse,
  UserLeaguesResponse,
} from '../types';

function identityParams(): URLSearchParams | null {
  const params = new URLSearchParams();
  const identity = savedLeagueIdentity();

  if (identity.leagueId && identity.rosterId) {
    params.set('league_id', identity.leagueId);
    params.set('roster_id', identity.rosterId);
    return params;
  }

  if (!identity.username) return null;
  params.set('username', identity.username);
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
  const query = params.toString();
  const response = await fetch(query ? `${path}?${query}` : path, requestInit(signal));
  const payload = (await response.json()) as T;
  if (!response.ok) {
    throw new Error(payload.error || `Request failed (${response.status}).`);
  }
  return payload;
}

function commonParams(week: WeekWindow, mode: DataMode): URLSearchParams {
  const params = identityParams();
  if (!params) throw new MissingIdentityError();
  params.set('week', week);
  params.set('mode', mode);
  return params;
}

export class MissingIdentityError extends Error {
  constructor() {
    super('No saved Sleeper league identity was found.');
    this.name = 'MissingIdentityError';
  }
}

export async function fetchUserLeagues(
  username: string,
  signal?: AbortSignal,
): Promise<UserLeaguesResponse> {
  const params = new URLSearchParams({ username, season: currentNflSeason() });
  return fetchJson<UserLeaguesResponse>('/user/leagues', params, signal);
}

export async function fetchLeagueResolution(
  leagueId: string,
  signal?: AbortSignal,
): Promise<LeagueResolution> {
  const params = new URLSearchParams({ league_id: leagueId });
  return fetchJson<LeagueResolution>('/league/resolve', params, signal);
}

export async function fetchProjections(
  week: WeekWindow,
  mode: DataMode,
  signal?: AbortSignal,
): Promise<ProjectionResponse> {
  return fetchJson<ProjectionResponse>('/projections', commonParams(week, mode), signal);
}

export async function fetchPlayerDetails(
  name: string,
  week: WeekWindow,
  mode: DataMode,
  signal?: AbortSignal,
): Promise<PlayerOddsDetails> {
  const params = commonParams(week, mode);
  params.set('name', name);
  return fetchJson<PlayerOddsDetails>('/player/odds', params, signal);
}

export async function fetchDefenses(
  week: WeekWindow,
  mode: DataMode,
  signal?: AbortSignal,
): Promise<DefenseResponse> {
  return fetchJson<DefenseResponse>('/defenses', commonParams(week, mode), signal);
}

export async function fetchBestLineup(
  week: WeekWindow,
  target: LineupTarget,
  mode: DataMode,
  signal?: AbortSignal,
): Promise<LineupResponse> {
  const params = commonParams(week, mode);
  params.set('target', target);
  return fetchJson<LineupResponse>('/best-lineup', params, signal);
}
