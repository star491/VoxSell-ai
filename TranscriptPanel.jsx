export default function TranscriptPanel({ turns, bottomRef }) {
  return (
    <div className="transcript">
      {turns.length === 0 && (
        <p className="transcript__empty">The conversation will appear here once the call starts.</p>
      )}
      {turns.map((turn, i) => (
        <div key={i} className={`bubble bubble--${turn.role}`}>
          <span className="bubble__speaker">{turn.role === "agent" ? "Alex" : "Customer"}</span>
          <p className="bubble__text">{turn.text}</p>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
