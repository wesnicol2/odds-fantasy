import { metricLabel } from '../analysis/metrics';
import { formatOdds } from '../analysis/odds';
import { useWorkspaceStore } from '../state/workspace';
import type { PlayerOddsDetails } from '../types';

interface PlayerBookEvidenceProps {
  details: PlayerOddsDetails | null;
  detailsLoading: boolean;
}

function formatValue(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function providerLabel(provider: string | null | undefined): string | null {
  if (!provider) return null;
  if (provider === 'odds_api') return 'The Odds API';
  if (provider === 'polymarket') return 'Polymarket';
  if (provider === 'kalshi') return 'Kalshi';
  return provider;
}

export function PlayerBookEvidence({ details, detailsLoading }: PlayerBookEvidenceProps) {
  const oddsFormat = useWorkspaceStore((state) => state.oddsFormat);
  const books = details?.books ?? [];
  const issues = details?.data_issues ?? [];
  const status = details?.data_status ?? 'ok';

  return (
    <div className="inspector-section book-evidence-section">
      <div className="section-label">Books &amp; sources</div>

      {status === 'fetch_failed' ? (
        <div className="source-status source-status-error">
          <strong>Odds fetch failed.</strong>
          <span>
            The sportsbook request for this player&apos;s game failed. Any sources below are
            partial evidence; an empty list is not proof that no betting lines exist.
          </span>
        </div>
      ) : status === 'degraded' ? (
        <div className="source-status">
          <strong>Some odds sources had problems.</strong>
          <span>Available source lines are shown below; coverage may be incomplete.</span>
        </div>
      ) : null}

      {detailsLoading && !details ? (
        <p className="subtle evidence-status">Loading book evidence…</p>
      ) : null}

      {!detailsLoading && books.length === 0 ? (
        <div className="empty-state">
          {status === 'fetch_failed'
            ? 'No source lines were available after the failed fetch.'
            : 'No source lines were returned for this player.'}
        </div>
      ) : null}

      {books.length ? (
        <div className="book-evidence-list">
          {books.map((book) => {
            const provider = providerLabel(book.provider);
            return (
              <details className="book-evidence-card" key={book.book}>
                <summary>
                  <span className="book-evidence-name">
                    <strong>{book.book}</strong>
                    {provider ? <small>{provider}</small> : null}
                  </span>
                  <span className="book-evidence-count">
                    {book.lines.length} {book.lines.length === 1 ? 'line' : 'lines'}
                  </span>
                </summary>
                <div className="evidence-table-scroll book-lines">
                  <table
                    className="evidence-table"
                    aria-label={
                      book.book + ' lines for ' + (details?.player.name ?? 'selected player')
                    }
                  >
                    <thead>
                      <tr>
                        <th>Market</th>
                        <th>Type</th>
                        <th className="number">Line</th>
                        <th className="number">Over</th>
                        <th className="number">Under</th>
                      </tr>
                    </thead>
                    <tbody>
                      {book.lines.map((line, index) => (
                        <tr
                          key={[
                            line.market_key,
                            line.source,
                            line.point,
                            line.over_odds,
                            line.under_odds,
                            index,
                          ].join(':')}
                        >
                          <td>{metricLabel(line.market_key)}</td>
                          <td>{line.source === 'alternate' ? 'Alt' : 'Main'}</td>
                          <td className="number">{formatValue(line.point)}</td>
                          <td className="number">{formatOdds(line.over_odds, oddsFormat)}</td>
                          <td className="number">{formatOdds(line.under_odds, oddsFormat)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            );
          })}
        </div>
      ) : null}

      {issues.length ? (
        <details className="source-issues">
          <summary>
            Data source {issues.length === 1 ? 'issue' : 'issues'} ({issues.length})
          </summary>
          <ul>
            {issues.map((issue, index) => (
              <li
                key={[
                  issue.provider_id,
                  issue.code,
                  issue.game_id ?? '',
                  index,
                ].join(':')}
              >
                <strong>{providerLabel(issue.provider_id) ?? issue.provider_id}</strong>
                <span>{issue.message}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
