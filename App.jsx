import { useCallback, useEffect, useRef, useState } from "react";
import { useAudioStreamer } from "./hooks/useAudioStreamer";
import LeadScoreGauge from "./components/LeadScoreGauge";
import TranscriptPanel from "./components/TranscriptPanel";
import InsightFeed from "./components/InsightFeed";
import CallSummary from "./components/CallSummary";
import "./App.css";

const WS_URL = import.meta.env.VITE_BACKEND_WS_URL || "ws://localhost:8000/ws";

const STATUS_LABEL = {
  idle: "Not connected",
  connecting: "Connecting\u2026",
  live: "Live",
  ended: "Call ended",
  error: "Connection error",
};

const timestamp = () => {
  const d = new Date();
  return `${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
};

export default function App() {
  const [turns, setTurns] = useState([]);
  const [score, setScore] = useState(50);
  const [category, setCategory] = useState("Warm");
  const [events, setEvents] = useState([]);
  const [summary, setSummary] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const bottomRef = useRef(null);

  const handleEvent = useCallback((payload) => {
    switch (payload.type) {
      case "transcript":
        setTurns((prev) => [...prev, { role: payload.role, text: payload.text }]);
        break;
      case "lead_score":
        setScore(payload.score);
        setCategory(payload.category);
        break;
      case "objection_detected":
        setScore(payload.lead_score);
        setCategory(payload.category);
        setEvents((prev) => [
          ...prev,
          { kind: "objection", label: `${payload.objection.toUpperCase()} objection detected`, time: timestamp() },
        ]);
        break;
      case "tool_call":
        setEvents((prev) => [...prev, { kind: "tool", label: describeToolCall(payload), time: timestamp() }]);
        break;
      case "call_summary":
        setSummary(payload);
        break;
      case "error":
        setErrorMessage(payload.message);
        break;
      default:
        break;
    }
  }, []);

  const { status, isSpeaking, startCall, endCall } = useAudioStreamer({ wsUrl: WS_URL, onEvent: handleEvent });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const handlePrimaryAction = () => {
    setErrorMessage(null);
    if (status === "idle" || status === "ended" || status === "error") {
      setTurns([]);
      setEvents([]);
      setSummary(null);
      setScore(50);
      setCategory("Warm");
      startCall();
    } else {
      endCall();
    }
  };

  const callIsActive = status === "connecting" || status === "live";

  return (
    <div className="app">
      <header className="app__header">
        <div>
          <p className="app__eyebrow">VoxSell AI</p>
          <h1 className="app__title">Live call console</h1>
        </div>
        <div className={`status status--${status}`}>
          <span className="status__dot" />
          {STATUS_LABEL[status]}
        </div>
      </header>

      {errorMessage && <div className="banner banner--error">{errorMessage}</div>}

      <main className="app__grid">
        <section className="panel panel--transcript">
          <div className="panel__header">
            <h2>Transcript</h2>
            {isSpeaking && <span className="listening-pulse">listening</span>}
          </div>
          <TranscriptPanel turns={turns} bottomRef={bottomRef} />
          <button className={`call-button call-button--${callIsActive ? "end" : "start"}`} onClick={handlePrimaryAction}>
            {callIsActive ? "End call" : "Start call"}
          </button>
        </section>

        <section className="panel panel--sidebar">
          <LeadScoreGauge score={score} category={category} />
          <InsightFeed events={events} />
          {summary && <CallSummary summary={summary} />}
        </section>
      </main>
    </div>
  );
}

function describeToolCall(payload) {
  if (payload.name === "get_current_time") return "Checked the current time";
  if (payload.name === "get_product_info") return `Looked up product info: "${payload.args?.query ?? ""}"`;
  if (payload.name === "schedule_demo") return "Booked a demo";
  return `Called tool: ${payload.name}`;
}
