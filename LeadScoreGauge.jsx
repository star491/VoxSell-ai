function polarToCartesian(cx, cy, r, angleDeg) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function describeArc(cx, cy, r, startAngle, endAngle) {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`;
}

// -90deg = score 0 (far left), +90deg = score 100 (far right), like a speedometer's upper half.
const scoreToAngle = (score) => -90 + (Math.max(0, Math.min(100, score)) / 100) * 180;

const ZONE_COLOR = { Cold: "var(--cold)", Warm: "var(--warm)", Hot: "var(--hot)" };

export default function LeadScoreGauge({ score, category }) {
  const cx = 100;
  const cy = 100;
  const arcRadius = 85;
  const needleRadius = 64;
  const needleAngle = scoreToAngle(score);
  const needleTip = polarToCartesian(cx, cy, needleRadius, needleAngle);
  const zoneColor = ZONE_COLOR[category] || ZONE_COLOR.Cold;

  return (
    <div className="gauge">
      <div className="gauge__label">LEAD TEMP</div>
      <svg viewBox="0 0 200 112" className="gauge__svg" aria-hidden="true">
        <path d={describeArc(cx, cy, arcRadius, -90, -18)} className="gauge__zone gauge__zone--cold" />
        <path d={describeArc(cx, cy, arcRadius, -18, 36)} className="gauge__zone gauge__zone--warm" />
        <path d={describeArc(cx, cy, arcRadius, 36, 90)} className="gauge__zone gauge__zone--hot" />
        <line
          x1={cx}
          y1={cy}
          x2={needleTip.x}
          y2={needleTip.y}
          className="gauge__needle"
          style={{ stroke: zoneColor }}
        />
        <circle cx={cx} cy={cy} r="7" className="gauge__pivot" />
      </svg>
      <div className="gauge__readout">
        <span className="gauge__score">{score}</span>
        <span className="gauge__category" style={{ color: zoneColor }}>
          {category}
        </span>
      </div>
    </div>
  );
}
