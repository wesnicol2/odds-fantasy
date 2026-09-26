import { useEffect, useRef, useState } from 'react';
import { fetchLeagueResolution, fetchUserLeagues } from '../api/client';
import { getCookie, saveLeagueIdentity } from '../identity';
import type { LeagueResolution, SleeperLeagueSummary, SleeperLeagueTeam } from '../types';

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

function teamLabel(team: SleeperLeagueTeam): string {
  return team.team_name || team.display_name || `Team ${team.roster_id}`;
}

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

  const commitTeam = (
    resolvedLeague: LeagueResolution,
    leagueId: string,
    team: SleeperLeagueTeam,
  ) => {
    saveLeagueIdentity(username.trim(), leagueId, String(team.roster_id));
    onComplete({
      leagueName: resolvedLeague.name || leagueId,
      teamName: teamLabel(team),
    });
  };

  const resolveLeague = async (leagueId: string, ownerUserId: string) => {
    const payload = await fetchLeagueResolution(leagueId);
    if (!payload.teams.length) {
      throw new Error('No teams were found in that league.');
    }

    const ownedTeam = ownerUserId
      ? payload.teams.find((team) => team.owner_id === ownerUserId)
      : undefined;
    if (ownedTeam) {
      commitTeam(payload, leagueId, ownedTeam);
      return;
    }

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
        setError('No current leagues found for that username.');
        return;
      }

      const resolvedUserId = payload.user_id ?? '';
      setUsername(value);
      setUserId(resolvedUserId);
      setLeagues(payload.leagues);

      if (payload.leagues.length === 1 && resolvedUserId) {
        const leagueId = payload.leagues[0].league_id;
        setSelectedLeagueId(leagueId);
        await resolveLeague(leagueId, resolvedUserId);
      } else {
        setSelectedLeagueId('');
        setStep('league');
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load that Sleeper account.');
    } finally {
      setBusy(false);
    }
  };

  const chooseLeague = async (leagueId: string) => {
    setBusy(true);
    setError(null);
    setSelectedLeagueId(leagueId);
    try {
      await resolveLeague(leagueId, userId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load that league.');
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
    commitTeam(league, selectedLeagueId, team);
  };

  const setupTitle =
    step === 'username'
      ? 'Set up your league'
      : step === 'league'
        ? 'Choose a league'
        : 'Choose your team';

  return (
    <div className={`setup-backdrop${required ? ' setup-backdrop--required' : ''}`}>
      <section
        className={`setup-dialog${required ? ' setup-dialog--welcome' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="setup-title"
      >
        <header className="setup-header">
          <div>
            <span className="eyebrow">Odds Fantasy</span>
            <h2 id="setup-title">{setupTitle}</h2>
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

        {step === 'username' ? (
          <form
            className="setup-body setup-intro"
            onSubmit={(event) => {
              event.preventDefault();
              void submitUsername();
            }}
          >
            <div className="setup-pitch">
              <span className="setup-pitch-mark">↗</span>
              <div>
                <h3>Your lineup. Sharpened by the market.</h3>
                <p>Enter one Sleeper username and we’ll surface the start/sit calls worth checking.</p>
              </div>
            </div>
            <label className="setup-field setup-username-field">
              <span>Sleeper username</span>
              <div className="setup-username-row">
                <input
                  ref={usernameInputRef}
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="Your Sleeper username"
                  disabled={busy}
                />
                <button
                  type="submit"
                  className="primary-action"
                  aria-label="Continue"
                  disabled={busy}
                >
                  {busy ? 'Loading…' : 'Load my team'}
                </button>
              </div>
            </label>
            <p className="setup-footnote">
              No player-by-player setup. We use your existing Sleeper roster.
            </p>
          </form>
        ) : null}

        {step === 'league' ? (
          <form
            className="setup-body"
            onSubmit={(event) => {
              event.preventDefault();
              if (selectedLeagueId) void chooseLeague(selectedLeagueId);
              else setError('Choose a league.');
            }}
          >
            <div className="setup-step-copy">
              <strong>{username}</strong> is in {leagues.length} current{' '}
              {leagues.length === 1 ? 'league' : 'leagues'}.
            </div>
            <label className="setup-field">
              <span>League for {username}</span>
              <select
                value={selectedLeagueId}
                onChange={(event) => setSelectedLeagueId(event.target.value)}
                disabled={busy}
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
                {busy ? 'Loading…' : 'Continue'}
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
            <div className="setup-step-copy">
              Sleeper did not identify an owned roster automatically. Choose the team to use.
            </div>
            <label className="setup-field">
              <span>Team in {league.name || 'this league'}</span>
              <select
                value={selectedRosterId}
                onChange={(event) => setSelectedRosterId(event.target.value)}
              >
                <option value="">Choose a team…</option>
                {league.teams.map((row) => (
                  <option key={row.roster_id} value={String(row.roster_id)}>
                    {teamLabel(row)}
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
                Use this team
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
