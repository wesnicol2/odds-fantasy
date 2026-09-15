import type { DefenseRow } from '../types';

export type DefenseMeasure = 'implied' | 'floor' | 'mid' | 'ceiling';

export const MEASURE_LABELS: Record<DefenseMeasure, string> = {
  implied: 'Opponent implied total',
  floor: 'Floor',
  mid: 'Mid',
  ceiling: 'Ceiling',
};

function formatValue(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function formatSigned(value: number, digits = 1): string {
  const normalized = Math.abs(value) < 0.005 ? 0 : value;
  return `${normalized > 0 ? '+' : ''}${normalized.toFixed(digits)}`;
}

/** Headline results match the precision the ranked table shows. */
function formatResult(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toFixed(1);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/**
 * The arithmetic behind one defense number.
 *
 * Every value shown here is supplied by the backend alongside the number it
 * explains, so the explanation cannot drift from the ranked figure: this
 * component formats provenance, it never recomputes a projection.
 */
export function DefenseNumberExplainer({
  row,
  measure,
}: {
  row: DefenseRow;
  measure: DefenseMeasure;
}) {
  const books = row.implied_books ?? [];
  const breakdown = row.range_breakdown ?? null;

  if (measure === 'implied') {
    if (!books.length) {
      return (
        <div className="empty-state">
          No book posted both a game total and a spread for this game.
        </div>
      );
    }
    return (
      <div className="explain-block">
        <p className="explain-formula">implied total = game total ÷ 2 − opponent spread ÷ 2</p>
        <div className="decision-table-scroll">
          <table className="explain-table" aria-label="Opponent implied total by sportsbook">
            <thead>
              <tr>
                <th>Book</th>
                <th className="number">Game total</th>
                <th className="number">Opp. spread</th>
                <th className="number">Implied</th>
              </tr>
            </thead>
            <tbody>
              {books.map((line) => (
                <tr key={line.book}>
                  <td>{line.book}</td>
                  <td className="number">{formatValue(line.game_total)}</td>
                  <td className="number">{formatSigned(line.opponent_spread)}</td>
                  <td className="number">{formatValue(line.implied_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="explain-result">
          Median of {books.length} {books.length === 1 ? 'book' : 'books'} ={' '}
          <strong>{formatResult(row.implied_total)}</strong>
        </p>
        <p className="explain-note">
          The median is taken across books rather than a single book's line, and only books that
          posted both markets can contribute a row.
        </p>
      </div>
    );
  }

  if (!breakdown) {
    return <div className="empty-state">This defense has no modeled range to explain.</div>;
  }

  if (measure === 'mid') {
    return (
      <div className="explain-block">
        <p className="explain-formula">
          Mid = Σ P(opponent lands in bracket) × the league's points for that bracket
        </p>
        <p className="explain-note">
          Opponent points are modeled as a normal distribution centered on the implied total (
          {formatValue(breakdown.opponent_mean)}) with σ = {formatValue(breakdown.sigma)}.
        </p>
        <div className="decision-table-scroll">
          <table className="explain-table" aria-label="Mid by points-allowed bracket">
            <thead>
              <tr>
                <th>Points allowed</th>
                <th className="number">Chance</th>
                <th className="number">League pts</th>
                <th className="number">Contribution</th>
              </tr>
            </thead>
            <tbody>
              {breakdown.mid.brackets.map((bracket) => (
                <tr key={bracket.bracket}>
                  <td>{bracket.bracket_label}</td>
                  <td className="number">{formatPercent(bracket.probability)}</td>
                  <td className="number">{formatSigned(bracket.points)}</td>
                  <td className="number">{formatSigned(bracket.contribution, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="explain-result">
          Sum of contributions = <strong>{formatResult(breakdown.mid.points)}</strong>
        </p>
      </div>
    );
  }

  const pick = measure === 'floor' ? breakdown.floor : breakdown.ceiling;
  const worstCase = measure === 'floor';
  return (
    <div className="explain-block">
      <p className="explain-note">
        {worstCase
          ? 'A defense scores least when its opponent scores most, so the floor reads off the high opponent percentile.'
          : 'A defense scores most when its opponent scores least, so the ceiling reads off the low opponent percentile.'}
      </p>
      <dl className="explain-steps">
        <div>
          <dt>Opponent implied total</dt>
          <dd>{formatValue(breakdown.opponent_mean)}</dd>
        </div>
        <div>
          <dt>Assumed spread of team scores (σ)</dt>
          <dd>{formatValue(breakdown.sigma)}</dd>
        </div>
        <div>
          <dt>Opponent points at the {Math.round(pick.percentile * 100)}th percentile</dt>
          <dd>{formatValue(pick.opponent_points)}</dd>
        </div>
        <div>
          <dt>Points-allowed bracket that lands in</dt>
          <dd>{pick.bracket_label}</dd>
        </div>
        <div>
          <dt>Your league's points for that bracket</dt>
          <dd>{formatSigned(pick.points)}</dd>
        </div>
      </dl>
      <p className="explain-result">
        {MEASURE_LABELS[measure]} = <strong>{formatResult(pick.points)}</strong>
      </p>
    </div>
  );
}
