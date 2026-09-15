import { useState } from 'react';
import type { DefenseResponse, DefenseRow } from '../types';
import {
  type DefenseMeasure,
  DefenseNumberExplainer,
  MEASURE_LABELS,
} from './DefenseNumberExplainer';

interface DefenseViewProps {
  payload: DefenseResponse | null;
  loading: boolean;
  error: string | null;
}

const MEASURES: DefenseMeasure[] = ['implied', 'floor', 'mid', 'ceiling'];

function formatValue(value: number | null): string {
  return value === null ? '—' : value.toFixed(1);
}

function measureValue(row: DefenseRow, measure: DefenseMeasure): number | null {
  if (measure === 'implied') return row.implied_total;
  if (measure === 'floor') return row.floor;
  if (measure === 'mid') return row.mid;
  return row.ceiling;
}

function formatKickoff(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(date);
}

function ownershipLabel(row: DefenseRow): string {
  if (row.owned_by_current) return 'Yours';
  if (row.taken) return row.owner ? `Taken · ${row.owner}` : 'Taken';
  return 'Available';
}

function ownershipClass(row: DefenseRow): string {
  if (row.owned_by_current) return 'yours';
  if (row.taken) return 'taken';
  return 'available';
}

/** A ranked number that opens its own derivation when selected. */
function DerivedValue({
  row,
  measure,
  selected,
  onSelect,
}: {
  row: DefenseRow;
  measure: DefenseMeasure;
  selected: boolean;
  onSelect: (defense: string, measure: DefenseMeasure) => void;
}) {
  const value = measureValue(row, measure);
  if (value === null) return <span className="subtle">—</span>;
  return (
    <button
      type="button"
      className={selected ? 'derived-value selected' : 'derived-value'}
      onClick={() => onSelect(row.defense, measure)}
      aria-label={`Explain ${row.defense} ${MEASURE_LABELS[measure].toLowerCase()} ${formatValue(value)}`}
    >
      {formatValue(value)}
    </button>
  );
}

function DefenseDetail({
  row,
  measure,
  onSelectMeasure,
  onExit,
}: {
  row: DefenseRow;
  measure: DefenseMeasure;
  onSelectMeasure: (measure: DefenseMeasure) => void;
  onExit: () => void;
}) {
  return (
    <aside className="defense-detail" aria-label="Defense detail">
      <header className="comparison-heading">
        <div>
          <div className="section-label">Defense detail</div>
          <h2>{row.defense}</h2>
          <p className="defense-detail-matchup">
            vs {row.opponent} · {formatKickoff(row.game_date)}
          </p>
        </div>
        <button type="button" onClick={onExit}>
          Close
        </button>
      </header>

      <div className="defense-detail-meta">
        <span className={`ownership ${ownershipClass(row)}`}>{ownershipLabel(row)}</span>
        <span className="subtle">
          {row.book_count} {row.book_count === 1 ? 'book' : 'books'} priced this game
        </span>
      </div>

      <p className="defense-detail-copy">
        Every number below is derived. Select one to see the exact inputs it was derived from.
      </p>

      <fieldset className="defense-measure-strip">
        <legend className="sr-only">Defense numbers</legend>
        {MEASURES.map((option) => {
          const value = measureValue(row, option);
          return (
            <button
              key={option}
              type="button"
              className={option === measure ? 'defense-measure active' : 'defense-measure'}
              onClick={() => onSelectMeasure(option)}
              disabled={value === null}
            >
              <span>{MEASURE_LABELS[option]}</span>
              <strong>{formatValue(value)}</strong>
            </button>
          );
        })}
      </fieldset>

      <section className="defense-explain" aria-label={`${MEASURE_LABELS[measure]} derivation`}>
        <h3>How {MEASURE_LABELS[measure].toLowerCase()} is calculated</h3>
        <DefenseNumberExplainer row={row} measure={measure} />
      </section>

      <p className="decision-note">
        Defense Floor/Mid/Ceiling price only the points-allowed component. Sacks, turnovers and
        defensive touchdowns are not modeled.
      </p>
    </aside>
  );
}

export function DefenseView({ payload, loading, error }: DefenseViewProps) {
  const [selected, setSelected] = useState<{ defense: string; measure: DefenseMeasure } | null>(
    null,
  );

  const selectedRow = selected
    ? (payload?.defenses.find((row) => row.defense === selected.defense) ?? null)
    : null;

  const selectNumber = (defense: string, measure: DefenseMeasure) =>
    setSelected({ defense, measure });

  return (
    <main
      className={selectedRow ? 'decision-view defense-view detailed' : 'decision-view defense-view'}
      aria-label="Defense analysis"
    >
      <header className="decision-heading">
        <div>
          <span className="eyebrow">Matchup ranking</span>
          <h2>Defenses</h2>
          <p>
            Lower opponent implied team total is the stronger market matchup. Select any number to
            open the math behind it.
          </p>
        </div>
        {payload?.ratelimit ? <span className="decision-meta">{payload.ratelimit}</span> : null}
      </header>

      {loading ? <div className="decision-loading">Loading spread and total markets…</div> : null}
      {error ? <div className="error-state">{error}</div> : null}
      {!error && payload?.message ? <div className="status-note">{payload.message}</div> : null}
      {!loading && !error && payload ? (
        <div className="defense-layout">
          <div className="defense-table-pane">
            <div className="decision-table-scroll">
              <table className="decision-table defense-table">
                <thead>
                  <tr>
                    <th>Defense</th>
                    <th>Opponent</th>
                    <th className="number">Opp. implied</th>
                    <th className="number">Floor</th>
                    <th className="number">Mid</th>
                    <th className="number">Ceiling</th>
                    <th className="number">Books</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.defenses.map((row) => {
                    const active = selected?.defense === row.defense;
                    return (
                      <tr
                        key={row.defense}
                        className={`${row.implied_total === null ? 'unavailable' : ''} ${
                          active ? 'selected' : ''
                        }`}
                      >
                        <td>
                          <strong>{row.abbr || row.defense}</strong>
                          <span className="row-secondary">{row.defense}</span>
                        </td>
                        <td>{row.opponent}</td>
                        {MEASURES.map((measure) => (
                          <td
                            key={measure}
                            className={
                              measure === 'implied' ? 'number primary-decision-value' : 'number'
                            }
                          >
                            <DerivedValue
                              row={row}
                              measure={measure}
                              selected={Boolean(active && selected?.measure === measure)}
                              onSelect={selectNumber}
                            />
                          </td>
                        ))}
                        <td className="number">
                          {row.book_count ? (
                            <button
                              type="button"
                              className="derived-value"
                              onClick={() => selectNumber(row.defense, 'implied')}
                              aria-label={`Explain ${row.defense} book count ${row.book_count}`}
                            >
                              {row.book_count}
                            </button>
                          ) : (
                            <span className="subtle">0</span>
                          )}
                        </td>
                        <td>
                          <span className={`ownership ${ownershipClass(row)}`}>
                            {ownershipLabel(row)}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {payload.note ? <p className="decision-note">{payload.note}</p> : null}
          </div>

          {selectedRow && selected ? (
            <DefenseDetail
              row={selectedRow}
              measure={selected.measure}
              onSelectMeasure={(measure) => selectNumber(selectedRow.defense, measure)}
              onExit={() => setSelected(null)}
            />
          ) : null}
        </div>
      ) : null}
    </main>
  );
}
