import type { DataMode } from '../state/workspace';

interface AppSettingsProps {
  dataMode: DataMode;
  onDataModeChange: (mode: DataMode) => void;
  onChangeLeague: () => void;
}

export function AppSettings({ dataMode, onDataModeChange, onChangeLeague }: AppSettingsProps) {
  return (
    <details className="app-settings">
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
          Auto reuses valid provider caches. Cache only makes no provider refresh. Force fresh bypasses
          reusable odds caches for newly loaded data.
        </p>
        <button type="button" onClick={onChangeLeague}>
          Change league
        </button>
      </div>
    </details>
  );
}
