import { useRef } from 'react';
import type { DataMode } from '../state/workspace';

interface AppSettingsProps {
  dataMode: DataMode;
  onDataModeChange: (mode: DataMode) => void;
  onChangeLeague: () => void;
}

export function AppSettings({ dataMode, onDataModeChange, onChangeLeague }: AppSettingsProps) {
  const detailsRef = useRef<HTMLDetailsElement | null>(null);

  const handleChangeLeague = () => {
    if (detailsRef.current) detailsRef.current.open = false;
    onChangeLeague();
  };

  return (
    <details ref={detailsRef} className="app-settings">
      <summary>Settings</summary>
      <div className="settings-popover">
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
        <button type="button" onClick={handleChangeLeague}>
          Change league
        </button>
      </div>
    </details>
  );
}
