import { useRef } from 'react';
import type { OddsFormat } from '../analysis/odds';
import { type DataMode, useWorkspaceStore } from '../state/workspace';

interface AppSettingsProps {
  dataMode: DataMode;
  onDataModeChange: (mode: DataMode) => void;
  onChangeLeague: () => void;
}

export function AppSettings({ dataMode, onDataModeChange, onChangeLeague }: AppSettingsProps) {
  const detailsRef = useRef<HTMLDetailsElement | null>(null);
  const oddsFormat = useWorkspaceStore((state) => state.oddsFormat);
  const setOddsFormat = useWorkspaceStore((state) => state.setOddsFormat);

  const handleChangeLeague = () => {
    if (detailsRef.current) detailsRef.current.open = false;
    onChangeLeague();
  };

  return (
    <details ref={detailsRef} className="app-settings">
      <summary>Settings</summary>
      <div className="settings-popover">
        <label className="settings-field">
          <span>Odds display</span>
          <select
            value={oddsFormat}
            onChange={(event) => setOddsFormat(event.target.value as OddsFormat)}
          >
            <option value="american">American</option>
            <option value="decimal">Decimal</option>
          </select>
        </label>
        <p>American is the default. This changes display only; model inputs remain decimal.</p>
        <label className="settings-field">
          <span>Odds data</span>
          <select
            value={dataMode}
            onChange={(event) => onDataModeChange(event.target.value as DataMode)}
          >
            <option value="auto">Auto (cached)</option>
            <option value="cache">Cache only</option>
            <option value="fresh">Force fresh</option>
          </select>
        </label>
        <p>
          Auto reuses valid provider caches. Cache only makes no provider refresh. Force fresh
          bypasses reusable odds caches for newly loaded data.
        </p>
        <div className="settings-actions">
          <button type="button" onClick={handleChangeLeague}>
            Change league
          </button>
          <a className="settings-cache-link" href="/settings/cache">
            Cache
          </a>
        </div>
      </div>
    </details>
  );
}
