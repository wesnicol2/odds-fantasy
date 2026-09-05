import { useEffect, useState } from 'react';
import { fetchLeagueResolution, fetchUserLeagues } from '../api/client';
import { getCookie, saveLeagueIdentity } from '../identity';
import type { LeagueResolution, SleeperLeagueSummary } from '../types';

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
  const [leagues, setLeagues] = useState<SleeperLeagueSummary[]>([]);
  const [selectedLeagueId, setSelectedLeagueId] = useState('');
  const [league, setLeague] = useState<LeagueResolution | null>(null);
  const [selectedRosterId, setSelectedRosterId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setStep('username');
    setUsername(getCookie('sleeper_username') ?? '');
    setLeagues([]);
    setSelectedLeagueId('');
    setLeague(null);
    setSelectedRosterId('');
    setBusy(false);
    setError(null);
  }, [open]);

  if (!open) return null;

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
        setError('No leagues found for that username.');
        return;
      }
      setUsername(value);
      setLeagues(payload.leagues);
      setSelectedLeagueId('');
      setStep('league');
    } catch {
      setError('Could not load leagues for that username.');
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
      const payload = await fetchLeagueResolution(selectedLeagueId);
      if (!payload.teams.length) {
        setError('No teams were found in that league.');
        return;
      }
      setLeague(payload);
      setSelectedRosterId('');
      setStep('team');
    } catch {
      setError('Could not load that league.');
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
    saveLeagueIdentity(username, selectedLeagueId, selectedRosterId);
    onComplete({
      leagueName: league.name || selectedLeagueId,
      teamName: team.team_name || team.display_name || `Team ${selectedRosterId}`,
    });
  };

  return (
    <div className="setup-backdrop">
      <section className="setup-dialog" role="dialog" aria-modal="true" aria-labelledby="setup-title">
        <header className="setup-header">
          <div>
            <span className="eyebrow">Sleeper identity</span>
            <h2 id="setup-title">Set up your league</h2>
          </div>
          {!required ? (
            <button type="button" className="setup-close" onClick={onClose} aria-label="Close league setup">
              ×
            </button>
          ) : null}
        </header>

        <div className="setup-progress" aria-label="Setup progress">
          <span className={step === 'username' ? 'active' : ''}>1 Username</span>
          <span className={step === 'league' ? 'active' : ''}>2 League</span>
          <span className={step === 'team' ? 'active' : ''}>3 Team</span>
        </div>

        {step === 'username' ? (
          <form
            className="setup-body"
            onSubmit={(event) => {
              event.preventDefault();
              void submitUsername();
            }}
          >
            <label className="setup-field">
              <span>Sleeper username</span>
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Sleeper username"
                autoFocus
              />
            </label>
            <div className="setup-actions">
              <button type="submit" className="primary-action" disabled={busy}>
                {busy ? 'Finding leagues…' : 'Continue'}
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
              <select value={selectedLeagueId} onChange={(event) => setSelectedLeagueId(event.target.value)}>
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
                {busy ? 'Loading teams…' : 'Continue'}
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
              <select value={selectedRosterId} onChange={(event) => setSelectedRosterId(event.target.value)}>
                <option value="">Choose a team…</option>
                {league.teams.map((row) => (
                  <option key={row.roster_id} value={String(row.roster_id)}>
                    {row.team_name || row.display_name || `Team ${row.roster_id}`}
                  </option>
                ))}
              </select>
            </label>
            <div className="setup-actions split-actions">
              <button type="button" onClick={() => setStep('league')}>
                Back
              </button>
              <button type="submit" className="primary-action">
                Use this team
              </button>
            </div>
          </form>
        ) : null}

        {error ? <div className="setup-error" role="alert">{error}</div> : null}
      </section>
    </div>
  );
}
