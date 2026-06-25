export default function InsightFeed({ events }) {
  return (
    <div className="insights">
      <h4 className="insights__title">Live insights</h4>
      {events.length === 0 && (
        <p className="insights__empty">Objections and tool calls will show up here as they happen.</p>
      )}
      <ul className="insights__list">
        {events.map((event, i) => (
          <li key={i} className={`insights__item insights__item--${event.kind}`}>
            <span className="insights__icon" aria-hidden="true">
              {event.kind === "objection" ? "!" : "\u2699"}
            </span>
            <span className="insights__text">{event.label}</span>
            <time className="insights__time">{event.time}</time>
          </li>
        ))}
      </ul>
    </div>
  );
}
