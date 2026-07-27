import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { LANGS } from "./langs.js";

// Parse a Meet/Zoom URL, or a raw "platform/id" pair, into a room path.
function parseTarget(input) {
  const s = input.trim();
  const meet = s.match(/meet\.google\.com\/([a-z]{3}-[a-z]{4}-[a-z]{3})/i);
  if (meet) return { platform: "google_meet", id: meet[1] };
  const zoom = s.match(/zoom\.us\/(?:j|wc\/join)\/(\d+)/i);
  if (zoom) return { platform: "zoom", id: zoom[1] };
  const pair = s.match(/^(google_meet|zoom|teams|jitsi)\/(.+)$/i);
  if (pair) return { platform: pair[1].toLowerCase(), id: pair[2] };
  return null;
}

export default function Home() {
  const [input, setInput] = useState("");
  const [lang, setLang] = useState("vi");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  function open() {
    const t = parseTarget(input);
    if (!t) {
      setError("Dán link Google Meet / Zoom, hoặc nhập dạng google_meet/abc-defg-hij");
      return;
    }
    navigate(`/meet/${t.platform}/${encodeURIComponent(t.id)}?lang=${lang}`);
  }

  return (
    <div className="home">
      <div className="home-card">
        <h1>🎙️ Live Translate</h1>
        <p className="sub">Transcript trực tiếp + bản dịch realtime cho cuộc họp của bạn.</p>

        <label className="field-label">Link cuộc họp (bot đã join)</label>
        <input
          className="text-input"
          placeholder="https://meet.google.com/abc-defg-hij"
          value={input}
          onChange={(e) => { setInput(e.target.value); setError(""); }}
          onKeyDown={(e) => e.key === "Enter" && open()}
          autoFocus
        />

        <label className="field-label">Dịch sang</label>
        <select className="lang-select" value={lang} onChange={(e) => setLang(e.target.value)}>
          {LANGS.map((l) => (
            <option key={l.code} value={l.code}>{l.label}</option>
          ))}
        </select>

        {error && <div className="error">{error}</div>}

        <button className="primary-btn" onClick={open}>Xem realtime →</button>

        <p className="hint">
          Thông thường bot được mời vào phòng qua Slack, và link phòng này được gửi
          tự động vào thread. Bạn cũng có thể tự mở phòng bằng link cuộc họp ở trên.
        </p>
      </div>
    </div>
  );
}
