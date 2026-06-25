export default function CallSummary({ summary }) {
  if (!summary) return null;

  return (
    <div className="summary">
      <h3 className="summary__title">Call summary</h3>
      <p className="summary__text">{summary.summary}</p>
      <dl className="summary__stats">
        <div className="summary__stat">
          <dt>Final lead score</dt>
          <dd>
            {summary.final_score}/100 ({summary.category})
          </dd>
        </div>
        <div className="summary__stat">
          <dt>Objections raised</dt>
          <dd>{summary.objections_raised?.length ? summary.objections_raised.join(", ") : "None"}</dd>
        </div>
        <div className="summary__stat">
          <dt>Demo booked</dt>
          <dd>{summary.demo_booked ? "Yes" : "No"}</dd>
        </div>
        <div className="summary__stat">
          <dt>Call length</dt>
          <dd>{summary.duration_seconds}s</dd>
        </div>
      </dl>
    </div>
  );
}
