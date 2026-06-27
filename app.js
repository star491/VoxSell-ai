const SAMPLE_RATE_IN = 16000;
const SAMPLE_RATE_OUT = 24000;

const statusEl = document.querySelector("#status");
const connectButton = document.querySelector("#connectButton");
const talkButton = document.querySelector("#talkButton");
const stopAudioButton = document.querySelector("#stopAudioButton");
const planButton = document.querySelector("#planButton");
const leadButton = document.querySelector("#leadButton");
const sendTextButton = document.querySelector("#sendTextButton");
const textPrompt = document.querySelector("#textPrompt");
const logEl = document.querySelector("#log");
const meter = document.querySelector(".meter");

let ws;
let inputContext;
let outputContext;
let mediaStream;
let processor;
let sourceNode;
let isRecording = false;
let playbackTime = 0;
let scheduledSources = [];

connectButton.addEventListener("click", connect);
talkButton.addEventListener("pointerdown", startRecording);
talkButton.addEventListener("pointerup", stopRecording);
talkButton.addEventListener("pointerleave", stopRecording);
talkButton.addEventListener("touchcancel", stopRecording);
stopAudioButton.addEventListener("click", stopPlayback);
planButton.addEventListener("click", () =>
  sendText("Which VoxSell plan fits a 12 person sales team that needs lead scoring and follow ups?")
);
leadButton.addEventListener("click", () =>
  sendText(
    "Save Acme Retail as a lead. Contact is Riya. Pain point is missed follow ups from manual sales work. Budget is 6000 dollars, timeline is this month, team size is 14."
  )
);
sendTextButton.addEventListener("click", () => sendText(textPrompt.value));
textPrompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    sendText(textPrompt.value);
  }
});

function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.close();
    return;
  }

  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  setStatus("Connecting...");

  ws.addEventListener("open", () => {
    setStatus("Connected", "ready");
    connectButton.textContent = "Disconnect";
    setControlsEnabled(true);
    addLog("Status", "Backend WebSocket connected.");
  });

  ws.addEventListener("message", async (event) => {
    if (event.data instanceof ArrayBuffer) {
      await playPcmChunk(event.data);
      return;
    }

    const message = JSON.parse(event.data);
    handleServerMessage(message);
  });

  ws.addEventListener("close", () => {
    setStatus("Disconnected");
    connectButton.textContent = "Connect";
    setControlsEnabled(false);
    stopRecording();
    stopPlayback();
    addLog("Status", "Connection closed.");
  });

  ws.addEventListener("error", () => {
    setStatus("Connection error", "error");
    addLog("Error", "WebSocket connection failed.", "error");
  });
}

async function startRecording(event) {
  event?.preventDefault();
  if (!socketReady() || isRecording) return;

  stopPlayback();
  inputContext = inputContext || new AudioContext();
  outputContext = outputContext || new AudioContext({ sampleRate: SAMPLE_RATE_OUT });
  await inputContext.resume();
  await outputContext.resume();

  mediaStream = mediaStream || (await navigator.mediaDevices.getUserMedia({ audio: true }));
  sourceNode = inputContext.createMediaStreamSource(mediaStream);
  processor = inputContext.createScriptProcessor(4096, 1, 1);

  processor.onaudioprocess = (event) => {
    if (!isRecording || !socketReady()) return;
    const input = event.inputBuffer.getChannelData(0);
    const pcm = downsampleTo16BitPcm(input, inputContext.sampleRate, SAMPLE_RATE_IN);
    if (pcm.byteLength > 0) ws.send(pcm);
  };

  sourceNode.connect(processor);
  processor.connect(inputContext.destination);
  isRecording = true;
  talkButton.classList.add("recording");
  talkButton.textContent = "Listening";
  meter.classList.add("listening");
  addLog("Mic", "Streaming 16 kHz PCM audio. Interruptions will flush playback.");
}

function stopRecording() {
  if (!isRecording) return;

  isRecording = false;
  talkButton.classList.remove("recording");
  talkButton.textContent = "Hold to talk";
  meter.classList.remove("listening");

  if (processor) {
    processor.disconnect();
    processor.onaudioprocess = null;
    processor = null;
  }

  if (sourceNode) {
    sourceNode.disconnect();
    sourceNode = null;
  }

  if (socketReady()) {
    ws.send(JSON.stringify({ type: "audio_end" }));
  }
  addLog("Mic", "Stopped microphone stream.");
}

function sendText(text) {
  const trimmed = text.trim();
  if (!trimmed || !socketReady()) return;
  ws.send(JSON.stringify({ type: "text", text: trimmed }));
  addLog("You", trimmed);
  textPrompt.value = "";
}

function handleServerMessage(message) {
  if (message.type === "flush") {
    stopPlayback();
    addLog("Barge-in", "Playback flushed immediately.", "warn");
  } else if (message.type === "status") {
    setStatus(message.message, "ready");
    addLog("Status", message.message);
  } else if (message.type === "error") {
    setStatus("Error", "error");
    addLog("Error", String(message.message), "error");
  } else if (message.type === "input_transcript") {
    addLog("You said", message.text || "(transcribing)");
  } else if (message.type === "output_transcript" || message.type === "model_text") {
    addLog("VoxSell", message.text || "(speaking)");
  } else if (message.type === "tool") {
    addLog("Tool", `${message.name}: ${JSON.stringify(message.result)}`);
  } else if (message.type === "turn_complete") {
    addLog("Turn", "Gemini completed this response.");
  }
}

function downsampleTo16BitPcm(input, fromRate, toRate) {
  if (toRate === fromRate) {
    return floatTo16BitPcm(input);
  }

  const ratio = fromRate / toRate;
  const newLength = Math.floor(input.length / ratio);
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetInput = 0;

  while (offsetResult < result.length) {
    const nextOffsetInput = Math.floor((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;

    for (let i = offsetInput; i < nextOffsetInput && i < input.length; i += 1) {
      accum += input[i];
      count += 1;
    }

    result[offsetResult] = count > 0 ? accum / count : 0;
    offsetResult += 1;
    offsetInput = nextOffsetInput;
  }

  return floatTo16BitPcm(result);
}

function floatTo16BitPcm(float32Array) {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);

  for (let i = 0; i < float32Array.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }

  return buffer;
}

async function playPcmChunk(arrayBuffer) {
  outputContext = outputContext || new AudioContext({ sampleRate: SAMPLE_RATE_OUT });
  await outputContext.resume();

  const samples = new Int16Array(arrayBuffer);
  const audioBuffer = outputContext.createBuffer(1, samples.length, SAMPLE_RATE_OUT);
  const channel = audioBuffer.getChannelData(0);

  for (let i = 0; i < samples.length; i += 1) {
    channel[i] = samples[i] / 32768;
  }

  const source = outputContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(outputContext.destination);

  const startAt = Math.max(outputContext.currentTime, playbackTime);
  source.start(startAt);
  playbackTime = startAt + audioBuffer.duration;
  scheduledSources.push(source);
  source.addEventListener("ended", () => {
    scheduledSources = scheduledSources.filter((item) => item !== source);
  });
}

function stopPlayback() {
  scheduledSources.forEach((source) => {
    try {
      source.stop();
    } catch {
      // The source may already be stopped.
    }
  });
  scheduledSources = [];
  playbackTime = outputContext ? outputContext.currentTime : 0;
}

function setControlsEnabled(enabled) {
  talkButton.disabled = !enabled;
  stopAudioButton.disabled = !enabled;
  planButton.disabled = !enabled;
  leadButton.disabled = !enabled;
  sendTextButton.disabled = !enabled;
}

function setStatus(text, state) {
  statusEl.textContent = text;
  statusEl.classList.toggle("ready", state === "ready");
  statusEl.classList.toggle("error", state === "error");
}

function socketReady() {
  return ws && ws.readyState === WebSocket.OPEN;
}

function addLog(title, body, kind = "") {
  const entry = document.createElement("div");
  entry.className = `log-entry ${kind}`.trim();
  entry.innerHTML = `<strong></strong><span></span>`;
  entry.querySelector("strong").textContent = title;
  entry.querySelector("span").textContent = body;
  logEl.prepend(entry);
}
