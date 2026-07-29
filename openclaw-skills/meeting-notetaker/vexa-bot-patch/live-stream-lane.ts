/**
 * B-full live streaming lane — an ADDITIVE tap on the capture PCM.
 *
 * It streams the raw 16 kHz mono frames the bot already captures to the
 * soniox-bridge's `/v1/stream` relay, which keeps ONE persistent Soniox stream
 * per speaker channel (never windowed, never confirmed) and pushes a continuous,
 * seam-loss-free transcript straight to the live-translate app. This bypasses
 * Vexa's segmentation/confirm entirely for the LIVE view — the fix for long
 * monologues losing words at turn seams.
 *
 * It NEVER touches the normal Vexa transcription path: it only *reads* the same
 * frames `feedAudio` already receives, and every operation is wrapped so a
 * failure here can never disturb the meeting's real transcript. Config is derived
 * from the invocation (bridge URL + token + meeting id) — no new bot env needed.
 *
 * Wire protocol (bot -> bridge):
 *   binary frame = [1-byte channel][s16le PCM @16 kHz]
 *   text frame   = JSON control, e.g. {"type":"speaker","channel":N,"name":"..."}
 */
import type { Invocation } from './config.js';

export interface LiveStreamLane {
  /** Tap one capture frame (same args as BotPipeline.feedAudio, minus tsMs). */
  feed(channel: number, glowName: string | undefined, pcm: Float32Array): void;
  dispose(): Promise<void>;
}

/** http(s)://host:port[/...]  ->  ws(s)://host:port/v1/stream?platform&meeting&lang&token */
function wsUrlFromInv(inv: Invocation): string | null {
  const base = inv.transcriptionServiceUrl;
  if (!base || !inv.nativeMeetingId) return null;
  let origin: string;
  try {
    const u = new URL(base);
    origin = `${u.protocol === 'https:' ? 'wss:' : 'ws:'}//${u.host}`;
  } catch {
    return null;
  }
  const q = new URLSearchParams({
    platform: String(inv.platform),
    meeting: String(inv.nativeMeetingId),
  });
  if (inv.language) q.set('lang', String(inv.language));
  if (inv.transcriptionServiceToken) q.set('token', String(inv.transcriptionServiceToken));
  return `${origin}/v1/stream?${q.toString()}`;
}

/** Float32 [-1,1] -> [1-byte channel][s16le PCM], one binary frame for the relay. */
function frameWithChannel(channel: number, pcm: Float32Array): Uint8Array {
  const out = new Uint8Array(1 + pcm.length * 2);
  out[0] = channel & 0xff;
  const view = new DataView(out.buffer, out.byteOffset, out.byteLength);
  for (let i = 0; i < pcm.length; i++) {
    let s = pcm[i];
    s = s < -1 ? -1 : s > 1 ? 1 : s;
    view.setInt16(1 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return out;
}

export function createLiveStreamLane(inv: Invocation): LiveStreamLane | null {
  if (inv.transcribeEnabled === false) return null;
  const url = wsUrlFromInv(inv);
  const WS: any = (globalThis as any).WebSocket;   // Node >=22 global; absent -> disable, never break the bot
  if (!url || !WS) return null;

  let ws: any = null;
  let ready = false;
  let disposed = false;
  let reconnectTimer: any = null;
  const speakers = new Map<number, string>();   // channel -> last speaker announced

  const sendSpeaker = (channel: number, name: string): void => {
    if (!ready || !ws) return;
    try { ws.send(JSON.stringify({ type: 'speaker', channel, name })); } catch { /* noop */ }
  };

  const scheduleReconnect = (): void => {
    if (disposed || reconnectTimer) return;
    reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, 1500);
  };

  function connect(): void {
    if (disposed || ws) return;
    try {
      ws = new WS(url);
      ws.binaryType = 'arraybuffer';
      ws.onopen = () => {
        ready = true;
        for (const [ch, name] of speakers) sendSpeaker(ch, name);   // re-announce after (re)connect
      };
      ws.onclose = () => { ready = false; ws = null; scheduleReconnect(); };
      ws.onerror = () => { try { ws?.close(); } catch { /* noop */ } };
    } catch {
      ws = null;
      scheduleReconnect();
    }
  }

  connect();

  return {
    feed(channel, glowName, pcm) {
      try {
        if (glowName && speakers.get(channel) !== glowName) {
          speakers.set(channel, glowName);
          sendSpeaker(channel, glowName);
        }
        if (!ready || !ws || !pcm || pcm.length === 0) return;
        ws.send(frameWithChannel(channel, pcm));
      } catch { /* the tap must never disturb capture */ }
    },
    async dispose() {
      disposed = true;
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      try { ws?.close(); } catch { /* noop */ }
      ws = null;
    },
  };
}
