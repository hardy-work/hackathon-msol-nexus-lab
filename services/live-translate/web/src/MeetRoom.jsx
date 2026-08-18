import React, { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { labelFor } from "./langs.js";

const STATUS = {
  connecting: { text: "Đang kết nối…", cls: "connecting" },
  live: { text: "● Đang nghe", cls: "live" },
  ended: { text: "Cuộc họp đã kết thúc", cls: "ended" },
  error: { text: "Mất kết nối — đang thử lại…", cls: "error" },
};

// Rebuild the original meeting URL from platform + native id so viewers can
// jump into the actual call. (Google Meet can't be embedded, so we open it in a
// new tab instead of iframing it.)
function meetingUrl(platform, id) {
  switch (platform) {
    case "google_meet":
      return `https://meet.google.com/${id}`;
    case "zoom":
      return `https://zoom.us/j/${id}`;
    case "teams":
      return `https://teams.microsoft.com/l/meetup-join/${id}`;
    default:
      return null;
  }
}

function platformName(platform) {
  return { google_meet: "Google Meet", zoom: "Zoom", teams: "Teams", jitsi: "Jitsi" }[platform] || platform;
}

export default function MeetRoom() {
  const { platform, nativeId } = useParams();
  const [searchParams] = useSearchParams();
  // The target language is fixed by the link (chosen once when the Slack link
  // is created). It is intentionally NOT switchable in-room, to keep one
  // shared, consistent translation for everyone watching.
  const lang = searchParams.get("lang") || "vi";

  // idx -> { idx, speaker, srcLang, original, translated }
  const [segments, setSegments] = useState(new Map());
  const [status, setStatus] = useState("connecting");
  const [copied, setCopied] = useState(false);
  // Fast "live" line pushed by soniox-bridge (B1), ahead of Vexa's confirmed text.
  const [interim, setInterim] = useState("");
  // Preview translation of `interim`, once it's stable long enough to translate.
  // Cleared whenever a new interim line arrives so a stale translation never
  // shows next to newer original text.
  const [interimTranslated, setInterimTranslated] = useState(null);

  const scrollRef = useRef(null);
  const stickToBottom = useRef(true);
  // Mirrors `interim` for the SSE handler below, which is set up once per
  // connection and would otherwise see a stale closed-over `interim` value.
  const interimRef = useRef("");
  useEffect(() => {
    interimRef.current = interim;
  }, [interim]);

  // (Re)connect the SSE stream whenever the room or target language changes.
  useEffect(() => {
    setSegments(new Map());
    setInterim("");
    setStatus("connecting");
    const url = `/api/rooms/${platform}/${encodeURIComponent(nativeId)}/stream?lang=${lang}`;
    const es = new EventSource(url);

    es.onopen = () => setStatus((s) => (s === "ended" ? s : "live"));
    es.onerror = () => setStatus((s) => (s === "ended" ? s : "error"));
    es.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }

      if (msg.type === "hello") {
        setStatus("live");
      } else if (msg.type === "segment") {
        setSegments((prev) => {
          const next = new Map(prev);
          const existing = next.get(msg.idx) || {};
          next.set(msg.idx, {
            idx: msg.idx,
            speaker: msg.speaker,
            srcLang: msg.lang,
            original: msg.text,
            translated: existing.translated ?? null,
          });
          return next;
        });
      } else if (msg.type === "translation") {
        setSegments((prev) => {
          const next = new Map(prev);
          const existing = next.get(msg.idx);
          if (existing) next.set(msg.idx, { ...existing, translated: msg.text });
          return next;
        });
      } else if (msg.type === "interim") {
        setInterim(msg.text || "");
        setInterimTranslated(null); // new original -> old preview no longer applies
      } else if (msg.type === "interim_translation") {
        setInterimTranslated((prev) => {
          // Only keep it if it's still translating the original currently on screen.
          return msg.for_text === interimRef.current ? msg.text : prev;
        });
      } else if (msg.type === "end") {
        setStatus("ended");
        setInterim("");
        setInterimTranslated(null);
      }
    };

    return () => es.close();
  }, [platform, nativeId, lang]);

  // Auto-scroll to newest, unless the user scrolled up to read history.
  const ordered = useMemo(
    () => [...segments.values()].sort((a, b) => a.idx - b.idx),
    [segments]
  );
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [ordered]);

  function onScroll() {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }

  function copyLink() {
    navigator.clipboard?.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  const st = STATUS[status] || STATUS.connecting;

  return (
    <div className="room">
      <header className="room-header">
        <div className="room-title">
          <span className="room-name">{platform} · {nativeId}</span>
          <span className={`status ${st.cls}`}>{st.text}</span>
        </div>
        <div className="room-controls">
          <span className="lang-fixed">Dịch sang <strong>{labelFor(lang)}</strong></span>
          {meetingUrl(platform, nativeId) && (
            <a className="join-btn" href={meetingUrl(platform, nativeId)} target="_blank" rel="noreferrer">
              ↗ Mở {platformName(platform)}
            </a>
          )}
          <button className="ghost-btn" onClick={copyLink}>
            {copied ? "Đã copy ✓" : "Copy link"}
          </button>
        </div>
      </header>

      <div className="cols-head">
        <div className="col-h">Bản gốc</div>
        <div className="col-h">{labelFor(lang)}</div>
      </div>

      <div className="transcript" ref={scrollRef} onScroll={onScroll}>
        {ordered.length === 0 && (
          <div className="empty">
            {status === "ended"
              ? "Không có nội dung nào được ghi lại."
              : "Đang chờ bot bắt đầu nghe… nội dung sẽ hiện ngay khi có người nói."}
          </div>
        )}
        {ordered.map((seg) => {
          // Segment is already in the target language (e.g. a Vietnamese
          // meeting on a lang=vi link) -> nothing to translate, so show one
          // full-width cell instead of two identical columns.
          const sameLang = !!seg.srcLang && seg.srcLang.toLowerCase() === lang.toLowerCase();
          return (
            <div className="turn" key={seg.idx}>
              <div className="speaker">{seg.speaker}{seg.srcLang ? ` · ${seg.srcLang}` : ""}</div>
              <div className="turn-cols">
                <div className={`cell original ${sameLang ? "full-width" : ""}`}>{seg.original}</div>
                {!sameLang && (
                  <div className={`cell translated ${seg.translated == null ? "pending" : ""}`}>
                    {seg.translated == null ? "…" : seg.translated}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {interim && status !== "ended" && (
        <div className="interim-bar" title="Bản nghe nhanh (chưa xác nhận)">
          <span className="interim-badge">🎤 đang nghe</span>
          <div className="interim-cols">
            <span className="interim-text">{interim}</span>
            <span className={`interim-text interim-translated ${interimTranslated == null ? "pending" : ""}`}>
              {interimTranslated == null ? "…" : interimTranslated}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
