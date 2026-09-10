type ThermometerOrientation = 'horizontal' | 'vertical';

interface RangeThermometerProps {
  floor: number;
  mid: number;
  ceiling: number;
  minimum: number;
  maximum: number;
  label: string;
  className?: string;
  orientation?: ThermometerOrientation;
}

export function rangePercent(value: number, minimum: number, maximum: number): number {
  if (maximum <= minimum) return 50;
  return Math.min(100, Math.max(0, ((value - minimum) / (maximum - minimum)) * 100));
}

/**
 * Floor / mid / ceiling shown as one shared-scale thermometer.
 *
 * The caller owns the scale so two glyphs drawn against the same minimum and
 * maximum stay directly comparable. Vertical is the orientation to reach for
 * when two of them sit side by side: a common baseline lets the eye compare
 * heights directly, which two horizontal bars in separate cells do not. This
 * is presentation only: every value is a backend percentile handed to CSS.
 */
export function RangeThermometer({
  floor,
  mid,
  ceiling,
  minimum,
  maximum,
  label,
  className,
  orientation = 'horizontal',
}: RangeThermometerProps) {
  const floorPercent = rangePercent(floor, minimum, maximum);
  const midPercent = rangePercent(mid, minimum, maximum);
  const ceilingPercent = rangePercent(ceiling, minimum, maximum);
  const span = Math.max(0, ceilingPercent - floorPercent);
  const vertical = orientation === 'vertical';

  const at = (percent: number) => (vertical ? { bottom: `${percent}%` } : { left: `${percent}%` });
  const segment = vertical
    ? { bottom: `${floorPercent}%`, height: `${span}%` }
    : { left: `${floorPercent}%`, width: `${span}%` };

  const classes = ['range-glyph'];
  if (vertical) classes.push('range-glyph-vertical');
  if (className) classes.push(className);

  return (
    <div className={classes.join(' ')} role="img" aria-label={label}>
      <span className="range-segment" style={segment} />
      <span className="range-end floor" style={at(floorPercent)} />
      <span className="range-mid" style={at(midPercent)} />
      <span className="range-end ceiling" style={at(ceilingPercent)} />
    </div>
  );
}
