import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./styles.css";

const API = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";
const LANGUAGE_OPTIONS = [
  "English",
  "Auto",
  "Chinese",
  "Japanese",
  "Korean",
  "German",
  "French",
  "Russian",
  "Portuguese",
  "Spanish",
  "Italian",
];

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return "—";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60).toString().padStart(2, "0");
  return minutes ? `${minutes}:${remainder}` : `${remainder}s`;
}

function formatDate(value) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

function apiUrl(path) {
  return `${API}${path}`;
}

function assetUrl(path) {
  return path.startsWith("http") ? path : `${new URL(API).origin}${path}`;
}

function Icon({ name, size = 18 }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };
  const icons = {
    wave: <><path d="M2 12h2l2-7 4 14 3-10 2 6 2-3h3" /></>,
    library: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z" /><path d="M4 5.5v16" /></>,
    microphone: <><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v4M8 22h8" /></>,
    history: <><path d="M3 12a9 9 0 1 0 3-6.7" /><path d="M3 4v5h5M12 7v5l3 2" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.64 2.64-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.02 1.56v.1h-3.74v-.1a1.7 1.7 0 0 0-1.02-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.64-2.64.06-.06A1.7 1.7 0 0 0 5.2 15 1.7 1.7 0 0 0 3.64 14H3.5v-3.74h.14A1.7 1.7 0 0 0 5.2 9.24a1.7 1.7 0 0 0-.34-1.88L4.8 7.3l2.64-2.64.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.02-1.56v-.1h3.74v.1a1.7 1.7 0 0 0 1.02 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.64 2.64-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.02h.1V14h-.1A1.7 1.7 0 0 0 19.4 15Z" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    upload: <><path d="M12 16V3M7 8l5-5 5 5M5 21h14" /></>,
    play: <><path d="m8 5 11 7-11 7z" /></>,
    trash: <><path d="M4 7h16M10 11v6M14 11v6M9 7l1-3h4l1 3M6 7l1 14h10l1-14" /></>,
    download: <><path d="M12 3v12M7 10l5 5 5-5M5 21h14" /></>,
    chevron: <><path d="m6 9 6 6 6-6" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    refresh: <><path d="M20 11a8.1 8.1 0 0 0-14.9-3L3 10M4 5v5h5M4 13a8.1 8.1 0 0 0 14.9 3L21 14M20 19v-5h-5" /></>,
    cpu: <><rect x="6" y="6" width="12" height="12" rx="1" /><path d="M9 1v5M15 1v5M9 18v5M15 18v5M1 9h5M1 15h5M18 9h5M18 15h5" /></>,
    check: <><path d="m5 12 4.5 4.5L19 7" /></>,
    warning: <><path d="M10.3 3.7 2.7 17a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></>,
  };
  return <svg {...common}>{icons[name] || icons.wave}</svg>;
}

function Waveform({ src, compact = false }) {
  const canvasRef = useRef(null);
  useEffect(() => {
    let active = true;
    const paint = async () => {
      if (!src || !canvasRef.current) return;
      const canvas = canvasRef.current;
      const ctx = canvas.getContext("2d");
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
      const width = rect.width;
      const height = rect.height;
      ctx.clearRect(0, 0, width, height);
      try {
        const response = await fetch(src);
        const data = await response.arrayBuffer();
        const audio = new AudioContext();
        const buffer = await audio.decodeAudioData(data);
        await audio.close();
        if (!active) return;
        const samples = Math.max(42, Math.floor(width / (compact ? 3.5 : 2.8)));
        const raw = buffer.getChannelData(0);
        const step = Math.max(1, Math.floor(raw.length / samples));
        const middle = height / 2;
        ctx.lineWidth = compact ? 1.35 : 1.7;
        ctx.strokeStyle = "#9a8cff";
        ctx.globalAlpha = 0.9;
        for (let index = 0; index < samples; index += 1) {
          let peak = 0;
          const start = index * step;
          for (let offset = 0; offset < step && start + offset < raw.length; offset += 1) peak = Math.max(peak, Math.abs(raw[start + offset]));
          const x = (index / samples) * width;
          const amplitude = Math.max(compact ? 2 : 3, peak * height * 0.82);
          ctx.beginPath();
          ctx.moveTo(x, middle - amplitude / 2);
          ctx.lineTo(x, middle + amplitude / 2);
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
      } catch {
        ctx.strokeStyle = "#6a6981";
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let x = 0; x < width; x += 3) {
          const y = height / 2 + Math.sin(x / 11) * 3;
          if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
    };
    paint();
    return () => { active = false; };
  }, [src, compact]);
  return <canvas className={`waveform ${compact ? "waveform-compact" : ""}`} ref={canvasRef} />;
}

function App() {
  const [page, setPage] = useState("synthesize");
  const [voices, setVoices] = useState([]);
  const [generations, setGenerations] = useState([]);
  const [device, setDevice] = useState(null);
  const [selectedVoice, setSelectedVoice] = useState("");
  const [text, setText] = useState("Good morning. I’ve mapped your day, protected the room you need to think, and kept the next step beautifully simple.");
  const [language, setLanguage] = useState("English");
  const [speed, setSpeed] = useState(1);
  const [output, setOutput] = useState(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState(null);
  const [voiceDialogOpen, setVoiceDialogOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [voicesResponse, generationsResponse, healthResponse] = await Promise.all([
        fetch(apiUrl("/voices")),
        fetch(apiUrl("/generations")),
        fetch(apiUrl("/health")),
      ]);
      if (!voicesResponse.ok) throw new Error("Unable to reach the local voice service.");
      const voicePayload = await voicesResponse.json();
      const generationPayload = await generationsResponse.json();
      const healthPayload = await healthResponse.json();
      setVoices(voicePayload.voices);
      setGenerations(generationPayload.generations);
      setDevice(healthPayload.device);
      setSelectedVoice(current => current || voicePayload.voices[0]?.id || "");
    } catch (error) {
      setNotice({ type: "error", message: error.message || "Unable to connect to the local service." });
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const selectedVoiceProfile = useMemo(() => voices.find(voice => voice.id === selectedVoice), [selectedVoice, voices]);

  async function generate() {
    if (!selectedVoice || !text.trim()) {
      setNotice({ type: "error", message: "Choose a voice and enter text before generating." });
      return;
    }
    setLoading(true);
    setNotice(null);
    try {
      const response = await fetch(apiUrl("/tts"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: selectedVoice, text: text.trim(), language, speed: Number(speed) }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Speech generation failed.");
      setOutput(payload);
      setGenerations(items => [payload, ...items]);
      setPage("synthesize");
      setNotice({ type: "success", message: "Speech generated locally and saved to your library." });
    } catch (error) {
      setNotice({ type: "error", message: error.message || "Speech generation failed." });
    } finally {
      setLoading(false);
    }
  }

  async function deleteVoice(voice) {
    if (!window.confirm(`Delete the “${voice.name}” profile and its source samples?`)) return;
    try {
      const response = await fetch(apiUrl(`/voices/${voice.id}`), { method: "DELETE" });
      if (!response.ok) throw new Error("Unable to delete the voice profile.");
      setVoices(items => items.filter(item => item.id !== voice.id));
      if (voice.id === selectedVoice) setSelectedVoice(voices.find(item => item.id !== voice.id)?.id || "");
      setNotice({ type: "success", message: "Voice profile removed from local storage." });
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  }

  const navItems = [
    ["library", "Voice Library", "library"],
    ["microphone", "Synthesize", "synthesize"],
    ["history", "Generations", "generations"],
    ["settings", "Settings", "settings"],
  ];

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><Icon name="wave" size={22} /></span><span>ATHENA</span></div>
        <p className="brand-subtitle">VOICE STUDIO</p>
        <nav className="nav-list" aria-label="Application sections">
          {navItems.map(([icon, label, key]) => <button key={key} className={`nav-item ${page === key ? "active" : ""}`} onClick={() => setPage(key)}><Icon name={icon} /><span>{label}</span></button>)}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-badge"><span className="status-dot" /><span>Local inference</span></div>
          <p>All voice files remain on this device.</p>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">{page === "synthesize" ? "CREATE / SYNTHESIZE" : page.toUpperCase()}</p><h1>{page === "synthesize" ? "Make it sound like you." : page === "library" ? "Your Voice Library" : page === "generations" ? "Generation History" : "Local Engine Settings"}</h1></div>
          <div className="topbar-actions">
            {device && <div className="device-pill" title={device.gpu_name || "CPU-only inference"}><Icon name="cpu" size={15} />{device.accelerator_available ? `${device.gpu_name} · ${device.vram_total_mb} MB` : "CPU mode"}</div>}
            <button className="primary-button compact" onClick={() => setVoiceDialogOpen(true)}><Icon name="plus" />New Voice</button>
          </div>
        </header>

        {notice && <div className={`notice ${notice.type}`}><Icon name={notice.type === "success" ? "check" : "warning"} /><span>{notice.message}</span><button onClick={() => setNotice(null)} aria-label="Dismiss"><Icon name="close" size={15} /></button></div>}

        {page === "synthesize" && <SynthesizePage voices={voices} selectedVoice={selectedVoice} setSelectedVoice={setSelectedVoice} selectedVoiceProfile={selectedVoiceProfile} text={text} setText={setText} language={language} setLanguage={setLanguage} speed={speed} setSpeed={setSpeed} output={output} loading={loading} onGenerate={generate} onNewVoice={() => setVoiceDialogOpen(true)} />}
        {page === "library" && <VoiceLibrary voices={voices} onNewVoice={() => setVoiceDialogOpen(true)} onDelete={deleteVoice} />}
        {page === "generations" && <GenerationList generations={generations} onSelect={item => { setOutput(item); setPage("synthesize"); }} />}
        {page === "settings" && <SettingsPanel device={device} />}
      </section>

      {voiceDialogOpen && <CreateVoiceDialog onClose={() => setVoiceDialogOpen(false)} onCreated={(voice) => { setVoices(items => [voice, ...items]); setSelectedVoice(voice.id); setVoiceDialogOpen(false); setPage("library"); setNotice({ type: "success", message: "Voice profile created and ready to synthesize." }); }} />}
    </main>
  );
}

function SynthesizePage({ voices, selectedVoice, setSelectedVoice, selectedVoiceProfile, text, setText, language, setLanguage, speed, setSpeed, output, loading, onGenerate, onNewVoice }) {
  return <div className="synthesize-grid">
    <section className="synth-card panel">
      <div className="section-heading"><div><p className="section-kicker">VOICE PROFILE</p><h2>Who’s speaking?</h2></div><button className="text-button" onClick={onNewVoice}><Icon name="plus" size={16} />Create Voice</button></div>
      {voices.length ? <label className="select-wrap"><select value={selectedVoice} onChange={event => setSelectedVoice(event.target.value)}>{voices.map(voice => <option value={voice.id} key={voice.id}>{voice.name}</option>)}</select><Icon name="chevron" size={18} /></label> : <div className="empty-inline"><Icon name="microphone" size={25} /><p>Create a voice profile from an authorized sample before synthesizing.</p><button className="secondary-button" onClick={onNewVoice}>Create first voice</button></div>}
      {selectedVoiceProfile && <div className="selected-voice"><button className="voice-play" onClick={() => new Audio(apiUrl(`/voices/${selectedVoiceProfile.id}/preview`)).play()} aria-label={`Preview ${selectedVoiceProfile.name}`}><Icon name="play" size={14} /></button><div><strong>{selectedVoiceProfile.name}</strong><span>{formatTime(selectedVoiceProfile.duration_seconds)} reference · {selectedVoiceProfile.reference_text ? "transcript attached" : "embedding mode"}</span></div><Waveform src={apiUrl(`/voices/${selectedVoiceProfile.id}/preview`)} compact /></div>}

      <div className="text-editor"><div className="editor-label"><label htmlFor="speech-text">WHAT SHOULD {selectedVoiceProfile?.name?.toUpperCase() || "THE VOICE"} SAY?</label><span>{text.length.toLocaleString()} / 5,000</span></div><textarea id="speech-text" value={text} onChange={event => setText(event.target.value.slice(0, 5000))} placeholder="Write naturally. Punctuation helps shape pauses and emphasis." /></div>
      <div className="controls-row"><label><span>Language</span><select value={language} onChange={event => setLanguage(event.target.value)}>{LANGUAGE_OPTIONS.map(item => <option key={item}>{item}</option>)}</select></label><label className="range-label"><span>Speaking speed <b>{Number(speed).toFixed(2)}×</b></span><input type="range" min="0.5" max="2" step="0.05" value={speed} onChange={event => setSpeed(event.target.value)} /><div className="range-scale"><span>Slower</span><span>Faster</span></div></label></div>
      <p className="control-note">Language is passed directly to Qwen3-TTS. Speed is applied locally after synthesis with pitch preservation. Other controls are intentionally omitted because the selected clone engine does not expose them as stable parameters.</p>
      <button className="generate-button" onClick={onGenerate} disabled={loading || !voices.length}>{loading ? <><span className="spinner" />Generating on your device…</> : <><Icon name="wave" />Generate Speech</>}</button>
    </section>

    <aside className="output-panel panel">
      <div className="section-heading"><div><p className="section-kicker">LATEST OUTPUT</p><h2>{output ? "Ready to hear" : "Waiting for a take"}</h2></div>{output && <button className="icon-button" onClick={onGenerate} title="Regenerate"><Icon name="refresh" /></button>}</div>
      {output ? <div className="output-content"><Waveform src={assetUrl(output.audio_url)} /><audio className="audio-player" src={assetUrl(output.audio_url)} controls autoPlay /><div className="output-metadata"><div><span>VOICE</span><b>{voices.find(item => item.id === output.voice_id)?.name || output.voice_id}</b></div><div><span>TIME</span><b>{output.generation_seconds.toFixed(2)} sec</b></div><div><span>MODEL</span><b>Qwen3-TTS Base</b></div><div><span>OUTPUT</span><b>{formatTime(output.duration_seconds)}</b></div></div><p className="output-text">“{output.text}”</p><div className="download-row"><a className="download-button" href={assetUrl(output.wav_download_url)}><Icon name="download" size={16} />WAV</a>{output.mp3_download_url && <a className="download-button muted" href={assetUrl(output.mp3_download_url)}><Icon name="download" size={16} />MP3</a>}</div></div> : <div className="output-empty"><div className="empty-orb"><Icon name="wave" size={34} /></div><h3>Your voice, in motion.</h3><p>Generate a new line to preview it here, then save the audio in your preferred format.</p></div>}
    </aside>
  </div>;
}

function VoiceLibrary({ voices, onNewVoice, onDelete }) {
  return <div><div className="page-intro"><p>Profiles combine your original authorized recordings with a clean reference prompt. Nothing is sent to a hosted TTS service.</p><button className="primary-button" onClick={onNewVoice}><Icon name="plus" />Create Voice</button></div>{voices.length ? <div className="voice-grid">{voices.map(voice => <article className="voice-card" key={voice.id}><div className="voice-card-top"><div className="voice-avatar">{voice.name.slice(0, 1).toUpperCase()}</div><button className="icon-button danger" onClick={() => onDelete(voice)} title="Delete voice"><Icon name="trash" size={17} /></button></div><h3>{voice.name}</h3><p>{formatTime(voice.duration_seconds)} cleaned reference · {voice.original_sample_count} original sample{voice.original_sample_count === 1 ? "" : "s"}</p><Waveform src={apiUrl(`/voices/${voice.id}/preview`)} compact /><div className="voice-card-footer"><span>Created {formatDate(voice.created_at)}</span><button className="play-text" onClick={() => new Audio(apiUrl(`/voices/${voice.id}/preview`)).play()}><Icon name="play" size={14} />Preview</button></div></article>)}</div> : <EmptyState icon="microphone" title="No voices yet" body="Add a clear recording of a voice you own or are explicitly authorized to reproduce." action="Create Voice" onAction={onNewVoice} />}</div>;
}

function GenerationList({ generations, onSelect }) {
  return generations.length ? <div className="generation-list panel">{generations.map(item => <button className="generation-row" onClick={() => onSelect(item)} key={item.id}><span className="generation-play"><Icon name="play" size={16} /></span><div className="generation-main"><strong>{item.text}</strong><span>{formatDate(item.created_at)} · {item.language} · {item.speed.toFixed(2)}×</span></div><div className="generation-stat"><span>GENERATION</span><b>{item.generation_seconds.toFixed(2)} sec</b></div><div className="generation-stat"><span>AUDIO</span><b>{formatTime(item.duration_seconds)}</b></div><Icon name="chevron" size={16} /></button>)}</div> : <EmptyState icon="history" title="No generations saved" body="Synthesized lines will appear here with audio playback and downloadable formats." />;
}

function SettingsPanel({ device }) {
  return <div className="settings-stack"><section className="panel settings-card"><div className="settings-icon"><Icon name="cpu" size={23} /></div><div><p className="section-kicker">INFERENCE DEVICE</p><h2>{device?.accelerator_available ? device.gpu_name : "CPU-only mode"}</h2><p>{device?.accelerator_available ? `${device.vram_total_mb} MB VRAM is available. Qwen3-TTS will remain loaded after its first generation.` : "No compatible CUDA GPU was detected. Local synthesis remains available but may be significantly slower."}</p></div><span className={`device-state ${device?.accelerator_available ? "ready" : "caution"}`}>{device?.accelerator_available ? "CUDA ready" : "CPU fallback"}</span></section><section className="panel settings-card"><div className="settings-icon"><Icon name="wave" size={23} /></div><div><p className="section-kicker">LOCAL MODEL</p><h2>{device?.model_id || "Qwen3-TTS Base"}</h2><p>Zero-shot clone prompts are stored in memory after first use while raw source recordings and all generated audio remain inside the local storage directory.</p></div><span className={`device-state ${device?.model_loaded ? "ready" : "neutral"}`}>{device?.model_loaded ? "Loaded" : "Loads on first use"}</span></section><section className="panel privacy-card"><Icon name="check" size={21} /><div><h3>Permission-based voice creation</h3><p>Creating a profile requires confirmation that you own the voice or have explicit permission to reproduce it. The app is built for personal, authorized use.</p></div></section></div>;
}

function EmptyState({ icon, title, body, action, onAction }) { return <section className="empty-state"><div className="empty-orb"><Icon name={icon} size={33} /></div><h2>{title}</h2><p>{body}</p>{action && <button className="primary-button" onClick={onAction}>{action}</button>}</section>; }

function CreateVoiceDialog({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [referenceText, setReferenceText] = useState("");
  const [files, setFiles] = useState([]);
  const [recording, setRecording] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);

  async function toggleRecording() {
    setError("");
    if (recording && recorderRef.current) { recorderRef.current.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = event => chunksRef.current.push(event.data);
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        const clip = new File([blob], `recording-${Date.now()}.webm`, { type: blob.type });
        setFiles(current => [...current, clip]);
        stream.getTracks().forEach(track => track.stop());
        setRecording(false);
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      setError("Microphone access was unavailable. You can still upload an audio file.");
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (!name.trim() || !files.length || !authorized) { setError("Enter a name, add a recording, and confirm your authorization."); return; }
    setSubmitting(true); setError("");
    const form = new FormData();
    form.append("name", name.trim());
    form.append("reference_text", referenceText.trim());
    form.append("authorization_acknowledged", String(authorized));
    files.forEach(file => form.append("files", file));
    try {
      const response = await fetch(apiUrl("/voices"), { method: "POST", body: form });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Unable to save this voice profile.");
      onCreated(payload.voice);
    } catch (requestError) { setError(requestError.message); } finally { setSubmitting(false); }
  }

  return <div className="modal-backdrop" role="presentation"><form className="voice-dialog" onSubmit={submit}><div className="dialog-header"><div><p className="section-kicker">NEW VOICE PROFILE</p><h2>Capture the reference</h2></div><button type="button" className="icon-button" onClick={onClose}><Icon name="close" /></button></div><p className="dialog-lead">For a natural clone, use one clear speaker in a quiet space. Aim for <strong>10–30 seconds</strong> of steady, conversational speech. Original files are retained locally.</p><label className="field-label">Voice name<input value={name} onChange={event => setName(event.target.value)} placeholder="e.g. Athena" maxLength="80" /></label><label className="field-label">Reference transcript <span>Recommended for best cloning</span><textarea value={referenceText} onChange={event => setReferenceText(event.target.value)} placeholder="Type the words spoken in the recording. If blank, the model uses speaker embedding mode with lower fidelity." maxLength="2000" /></label><div className="sample-actions"><label className="upload-zone"><input type="file" accept="audio/*" multiple onChange={event => setFiles(current => [...current, ...Array.from(event.target.files || [])])} /><Icon name="upload" size={20} /><span><b>Upload recordings</b><small>WAV, MP3, M4A, FLAC, OGG, AAC, or WebM</small></span></label><button type="button" className={`record-button ${recording ? "recording" : ""}`} onClick={toggleRecording}><Icon name="microphone" size={20} /><span>{recording ? "Stop recording" : "Record sample"}</span></button></div>{files.length > 0 && <div className="file-list">{files.map((file, index) => <div key={`${file.name}-${index}`}><Icon name="wave" size={15} /><span>{file.name}</span><small>{(file.size / 1024 / 1024).toFixed(1)} MB</small><button type="button" onClick={() => setFiles(current => current.filter((_, itemIndex) => itemIndex !== index))}><Icon name="close" size={14} /></button></div>)}</div>}<label className="consent"><input type="checkbox" checked={authorized} onChange={event => setAuthorized(event.target.checked)} /><span>I own this voice or have explicit permission from the voice owner to create and use this local profile.</span></label>{error && <p className="form-error"><Icon name="warning" size={15} />{error}</p>}<div className="dialog-footer"><button type="button" className="secondary-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={submitting}>{submitting ? "Preparing profile…" : "Save Voice"}</button></div></form></div>;
}

export default App;
