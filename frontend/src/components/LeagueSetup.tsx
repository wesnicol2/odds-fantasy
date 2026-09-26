import { useEffect, useRef, useState } from 'react';
import { fetchLeagueResolution, fetchUserLeagues } from '../api/client';
import { getCookie, saveLeagueIdentity } from '../identity';
import type {
  LeagueResolution,
  SleeperLeagueSummary,
  SleeperLeagueTeam,
} from '../types';

export interface LeagueSelectionSummary {
  leagueName: string;
  teamName: string;
}

interface LeagueSetupProps {
  open: boolean;
  required: boolean;
  onClose: () => void;
  onComplete: (summary: LeagueSelectionSummary) => void;
}

type SetupStep = 'username' | 'league' | 'team';

export function LeagueSetup({ open, required, onClose, onComplete }: LeagueSetupProps) {
  const [step, setStep] = useState<SetupStep>('username');
  const [username, setUsername] = useState('');
  const [userId, setUserId] = useState('');
  const [leagues, setLeagues] = useState<SleeperLeagueSummary[]>([]);
  const [selectedLeagueId, setSelectedLeagueId] = useState('');
  const [league, setLeague] = useState<LeagueResolution | null>(null);
  const [selectedRosterId, setSelectedRosterId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const usernameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setStep('username');
    setUsername(getCookie('sleeper_username') ?? '');
    setUserId('');
    setLeagues([]);
    setSelectedLeagueId('');
    setLeague(null);
    setSelectedRosterId('');
    setBusy(false);
    setError(null);
  }, [open]);

  useEffect(() => {
    if (!open || step !== 'username') return;
    usernameInputRef.current?.focus();
  }, [open, step]);

  if (!open) return null;

  const finishSelection = (
    leagueId: string,
    resolvedLeague: LeagueResolution,
    team: SleeperLeagueTeam,
  ) => {
    const rosterId = String(team.roster_id);
    saveLeagueIdentity(username, leagueId, rosterId);
    onComplete({
      leagueName: resolvedLeague.name || leagueId,
      teamName: team.team_name || team.display_name || `Team ${rosterId}`,
    });
  };

  const resolveLeagueForUser = async (leagueId: string, ownerId: string) => {
    const payload = await fetchLeagueResolution(leagueId);
    if (!payload.teams.length) {
      setError('No teams were found in that league.');
      return;
    }

    const ownedTeam = ownerId ? payload.teams.find((row) => row.owner_id === ownerId) : null;
    if (ownedTeam) {
      finishSelection(leagueId, payload, ownedTeam);
      return;
    }

    // This should be unusual, but a manual team picker is a safer fallback than
    // guessing when Sleeper does not identify the entered user as a roster owner.
    setLeague(payload);
    setSelectedRosterId('');
    setStep('team');
  };

  const submitUsername = async () => {
    const value = username.trim();
    if (!value) {
      setError('Enter a Sleeper username.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const payload = await fetchUserLeagues(value);
      if (!payload.leagues.length) {
        setError('No current NFL leagues found for that username.');
        return;
      }

      setUsername(value);
      setUserId(payload.user_id || '');
      setLeagues(payload.leagues);

      if (payload.leagues.length === 1 && payload.user_id) {
        const onlyLeague = payload.leagues[0];
        setSelectedLeagueId(onlyLeague.league_id);
        await resolveLeagueForUser(onlyLeague.league_id, payload.user_id);
        return;
      }

      setSelectedLeagueId('');
      setStep('league');
    } catch {
      setError('Could not load Sleeper leagues for that username.');
    } finally {
      setBusy(false);
    }
  };

  const submitLeague = async () => {
    if (!selectedLeagueId) {
      setError('Choose a league.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await resolveLeagueForUser(selectedLeagueId, userId);
    } catch {
      setError('Could not load that Sleeper league.');
    } finally {
      setBusy(false);
    }
  };

  const submitTeam = () => {
    if (!league || !selectedLeagueId || !selectedRosterId) {
      setError('Choose your team.');
      return;
    }
    const team = league.teams.find((row) => String(row.roster_id) === selectedRosterId);
    if (!team) {
      setError('Choose your team.');
      return;
    }
    finishSelection(selectedLeagueId, league, team);
  };

  const title =
    step === 'username'
      ? required
        ? 'Make the close calls easy.'
        : 'Change Sleeper league'
      : step === 'league'
        ? 'Pick a league.'
        : 'Pick your team.';

  return (
    <div className={`setup-backdrop ${required ? 'setup-backdrop-required' : ''}`}>
      <section
        className={`setup-dialog ${required ? 'setup-dialog-required' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label="Set up your league"
      >
        <header className="setup-header">
          <div>
            <span className="eyebrow">Odds Fantasy</span>
            <h2>{title}</h2>
            <p className="setup-intro">
              {step === 'username'
                ? 'Enter your Sleeper username. We’ll find your roster and surface the lineup decisions worth a second look.'
                : step === 'league'
                  ? `${leagues.length} leagues found for ${username}. Choose the one you want to sharpen.`
                  : 'Sleeper did not identify which roster is yours, so choose it once below.'}
            </p>
          </div>
          {!required ? (
            <button
              type="button"
              className="setup-close"
              onClick={onClose}
              aria-label="Close league setup"
            >
              ×
            </button>
          ) : null}
        </header>

        <div className="setup-step-label">
          {step === 'username'
            ? 'One username. No roster setup.'
            : step === 'league'
              ? 'Choose once — we remember it.'
              : 'Manual fallback'}
        </div>

        {step === 'username' ? (
          <form
            className="setup-body"
            onSubmit={(event) => {
              event.preventDefault();
              void submitUsername();
            }}
          >
            <label className="setup-field setup-field-primary">
              <span>Sleeper username</span>
              <input
                ref={usernameInputRef}
                type="text"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Your Sleeper username"
              />
            </label>
            <div className="setup-actions">
              <button type="submit" className="primary-action" disabled={busy}>
                {busy ? 'Finding your team…' : 'Find my team →'}
              </button>
            </div>
          </form>
        ) : null}

        {step === 'league' ? (
          <form
            className="setup-body"
            onSubmit={(event) => {
              event.preventDefault();
              void submitLeague();
            }}
          >
            <label className="setup-field">
              <span>League for {username}</span>
              <select
                value={selectedLeagueId}
                onChange={(event) => setSelectedLeagueId(event.target.value)}
              >
                <option value="">Choose a league…</option>
                {leagues.map((row) => (
                  <option key={row.league_id} value={row.league_id}>
                    {row.name || row.league_id}
                  </option>
                ))}
              </select>
            </label>
            <div className="setup-actions split-actions">
              <button type="button" onClick={() => setStep('username')} disabled={busy}>
                Back
              </button>
              <button type="submit" className="primary-action" disabled={busy}>
                {busy ? 'Opening league…' : 'Use this league →'}
              </button>
            </div>
          </form>
        ) : null}

        {step === 'team' && league ? (
          <form
            className="setup-body"
            onSubmit={(event) => {
              event.preventDefault();
              submitTeam();
            }}
          >
            <label className="setup-field">
              <span>Team in {league.name || 'this league'}</span>
              <select
                value={selectedRosterId}
                onChange={(event) => setSelectedRosterId(event.target.value)}
              >
                <option value="">Choose a team…</option>
                {league.teams.map((row) => (
                  <option key={row.roster_id} value={String(row.roster_id)}>
                    {row.team_name || row.display_name || `Team ${row.roster_id}`}
                  </option>
                ))}
              </select>
            </label>
            <div className="setup-actions split-actions">
              <button
                type="button"
                onClick={() => setStep(leagues.length > 1 ? 'league' : 'username')}
              >
                Back
              </button>
              <button type="submit" className="primary-action">
                Use this team →
              </button>
            </div>
          </form>
        ) : null}

        {error ? (
          <div className="setup-error" role="alert">
            {error}
          </div>
        ) : null}
      </section>
    </div>
  );
}
