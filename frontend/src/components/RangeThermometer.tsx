interface RangeThermometerProps {
  floor: number;
  mid: number;
  ceiling: number;
  minimum: number;
  maximum: number;
  label: string;
  className?: string;
}

export function rangePercent(value: number, minimum: number, maximum: number): number {
  if (maximum <= minimum) return 50;
  return Math.min(100, Math.max(0, ((value - minimum) / (maximum - minimum)) * 100));
}

/**
 * Floor / mid / ceiling shown as one shared-scale thermometer.
 *
 * The caller owns the scale so two glyphs drawn against the same minimum and
 * maximum stay directly comparable. This is presentation only: every value is
 * a backend percentile handed straight to CSS.
 */
export function RangeThermometer({
  floor,
  mid,
  ceiling,
  minimum,
  maximum,
  label,
  className,
}: RangeThermometerProps) {
  const floorPercent = rangePercent(floor, minimum, maximum);
  const midPercent = rangePercent(mid, minimum, maximum);
  const ceilingPercent = rangePercent(ceiling, minimum, maximum);

  return (
    <div
      className={className ? `range-glyph ${className}` : 'range-glyph'}
      role="img"
      aria-label={label}
    >
      <span
        className="range-segment"
        style={{
          left: `${floorPercent}%`,
          width: `${Math.max(0, ceilingPercent - floorPercent)}%`,
        }}
      />
      <span className="range-end floor" style={{ left: `${floorPercent}%` }} />
      <span className="range-mid" style={{ left: `${midPercent}%` }} />
      <span className="range-end ceiling" style={{ left: `${ceilingPercent}%` }} />
    </div>
  );
}
