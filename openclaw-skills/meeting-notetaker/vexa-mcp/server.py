"""MCP server bridging Vexa's meeting-bot REST API (self-hosted).

Lets an agent send a bot into a Google Meet / Zoom / Teams call, poll the
live transcript, check bot status, and stop the bot when the meeting ends.

Config (env vars):
  VEXA_BASE_URL  - e.g. http://<vexa-host>:18056 (default: http://localhost:18056)
  VEXA_API_KEY   - API key issued by your Vexa instance (sent as X-API-Key)
"""

import os
import re

import httpx
from mcp.server.fastmcp import FastMCP

VEXA_BASE_URL = os.environ.get("VEXA_BASE_URL", "http://localhost:18056")
VEXA_API_KEY = os.environ.get("VEXA_API_KEY", "")
# Public base URL of the live-translate web app (see ../live-translate). When
# set, join_meeting returns a ready-to-share room link so the skill can post it
# straight into the Slack thread. LIVE_TRANSLATE_LANG fixes the translation
# target for that link (not switchable by viewers, by design).
WEB_PUBLIC_URL = os.environ.get("WEB_PUBLIC_URL", "").rstrip("/")
LIVE_TRANSLATE_LANG = os.environ.get("LIVE_TRANSLATE_LANG", "vi")

mcp = FastMCP("vexa-bridge")

_client = httpx.Client(
    base_url=VEXA_BASE_URL,
    headers={"X-API-Key": VEXA_API_KEY},
    timeout=15.0,
)

_MEET_RE = re.compile(r"meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})", re.I)
_ZOOM_RE = re.compile(r"zoom\.us/(?:j|wc/join)/(\d+)", re.I)


def _parse_meeting_url(url: str) -> tuple[str, str]:
    """Return (platform, native_meeting_id) for a Meet or Zoom URL."""
    if m := _MEET_RE.search(url):
        return "google_meet", m.group(1)
    if m := _ZOOM_RE.search(url):
        return "zoom", m.group(1)
    raise ValueError(
        f"Could not parse platform/meeting id from URL: {url!r}. "
        "Pass platform and native_meeting_id explicitly instead."
    )


def _request(method: str, path: str, **kwargs) -> dict:
    resp = _client.request(method, path, **kwargs)
    resp.raise_for_status()
    return resp.json() if resp.content else {}


def _share_link(platform: str, native_meeting_id: str) -> str:
    """Live-translate room URL for this meeting, with the fixed target language.
    Empty string if WEB_PUBLIC_URL isn't configured."""
    if not WEB_PUBLIC_URL:
        return ""
    return f"{WEB_PUBLIC_URL}/meet/{platform}/{native_meeting_id}?lang={LIVE_TRANSLATE_LANG}"


@mcp.tool()
def join_meeting(
    meeting_url: str = "",
    platform: str = "",
    native_meeting_id: str = "",
    bot_name: str = "NexusBot",
    language: str = "",
) -> dict:
    """Send a bot into a Google Meet or Zoom call to start live transcription.

    Either pass `meeting_url` (parsed automatically), or pass `platform`
    ("google_meet" | "zoom" | "teams" | "jitsi") and `native_meeting_id`
    directly (required for Teams, or if URL parsing fails).

    IMPORTANT — after a successful join, the result contains a `share_link`
    field, e.g. "http://192.168.4.15:8080/meet/google_meet/abc-defg-hij?lang=vi".
    Your reply to the user MUST include that exact `share_link` URL — it is the
    live transcript + translation page everyone can open to watch together. Do
    NOT reply with only the Google Meet URL; the Meet link is NOT a substitute
    for `share_link`. Only omit it if `share_link` is empty/missing.
    """
    if meeting_url:
        platform, native_meeting_id = _parse_meeting_url(meeting_url)
    if not platform or not native_meeting_id:
        raise ValueError("Provide meeting_url, or both platform and native_meeting_id.")

    body = {
        "platform": platform,
        "native_meeting_id": native_meeting_id,
        "bot_name": bot_name,
    }
    if language:
        body["language"] = language
    resp = _request("POST", "/bots", json=body)
    # Attach the live-translate room link so the caller can post it to Slack
    # without re-deriving the URL. Also echo platform/native_meeting_id in case
    # the Vexa response omits them (the skill needs them for later calls).
    if isinstance(resp, dict):
        resp.setdefault("platform", platform)
        resp.setdefault("native_meeting_id", native_meeting_id)
        link = _share_link(platform, native_meeting_id)
        if link:
            resp["share_link"] = link
    return resp


@mcp.tool()
def get_transcript(platform: str, native_meeting_id: str) -> dict:
    """Fetch the current (or final) transcript for a meeting, with speaker labels."""
    return _request("GET", f"/transcripts/{platform}/{native_meeting_id}")


@mcp.tool()
def bot_status() -> dict:
    """List all bots currently running, across meetings."""
    return _request("GET", "/bots/status")


@mcp.tool()
def stop_meeting(platform: str, native_meeting_id: str) -> dict:
    """Remove the bot from a meeting, ending its participation."""
    return _request("DELETE", f"/bots/{platform}/{native_meeting_id}")


@mcp.tool()
def list_meetings() -> dict:
    """List meetings Vexa has captured (for finding past transcripts)."""
    return _request("GET", "/meetings")


if __name__ == "__main__":
    mcp.run()
