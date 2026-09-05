import { ProbabilityChart } from './components/ProbabilityChart';
import { useWorkspaceStore } from './state/workspace';

const views = [
  ['players', 'Players'],
  ['defenses', 'Defenses'],
  ['lineup', 'Best lineup'],
] as const;

export function App() {
  const view = useWorkspaceStore((state) => state.view);
  const week = useWorkspaceStore((state) => state.week);
  const target = useWorkspaceStore((state) => state.targetFantasyPoints);
  const selectedPlayer = useWorkspaceStore((state) => state.selectedPlayer);
  const setView = useWorkspaceStore((state) => state.setView);
  const setWeek = useWorkspaceStore((state) => state.setWeek);
  const setTarget = useWorkspaceStore((state) => state.setTargetFantasyPoints);

  return (
    <div className="app-frame">
      <header className="topbar">
        <div>
          <div className="eyebrow">Decision support</div>
          <h1>Odds Fantasy</h1>
        </div>
        <fieldset className="topbar-controls">
          <legend className="sr-only">Week window</legend>
          <button
            className={week === 'this' ? 'active' : ''}
            onClick={() => setWeek('this')}
            type="button"
          >
            This week
          </button>
          <button
            className={week === 'next' ? 'active' : ''}
            onClick={() => setWeek('next')}
            type="button"
          >
            Next week
          </button>
        </fieldset>
      </header>

      <nav className="primary-nav" aria-label="Analysis view">
        {views.map(([value, label]) => (
          <button
            key={value}
            className={view === value ? 'active' : ''}
            onClick={() => setView(value)}
            type="button"
          >
            {label}
          </button>
        ))}
      </nav>

      <main className="workspace">
        <aside className="ranking-pane" aria-label="Player ranking">
          <div className="pane-heading">
            <span className="eyebrow">Ranking</span>
            <h2>{view === 'players' ? 'Players' : view === 'defenses' ? 'Defenses' : 'Lineup'}</h2>
          </div>
          <div className="empty-state">
            The React workstation foundation is ready. API-backed ranking rows are the next
            migration slice.
          </div>
        </aside>

        <section className="analysis-pane" aria-label="Probability analysis">
          <div className="pane-heading split">
            <div>
              <span className="eyebrow">Probability</span>
              <h2>Fantasy points</h2>
            </div>
            <label className="target-control">
              <span>Target</span>
              <input
                type="number"
                inputMode="decimal"
                step="0.5"
                value={target ?? ''}
                placeholder="FP"
                onChange={(event) => {
                  const value = event.target.value;
                  setTarget(value === '' ? null : Number(value));
                }}
              />
            </label>
          </div>
          <ProbabilityChart series={[]} target={target} />
        </section>

        <aside className="inspector-pane" aria-label="Player inspector">
          <div className="pane-heading">
            <span className="eyebrow">Inspector</span>
            <h2>{selectedPlayer ?? 'No player selected'}</h2>
          </div>
          <div className="empty-state">
            Select a ranking row or probability series to inspect projections and sportsbook
            evidence without leaving the workspace.
          </div>
        </aside>
      </main>
    </div>
  );
}
