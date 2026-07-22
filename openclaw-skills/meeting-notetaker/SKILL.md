---
name: meeting-notetaker
description: Joins a Google Meet or Zoom call via a bot, transcribes it, and produces a structured meeting summary with action items.
homepage: https://github.com/hardy/hackathon-vexa-mcp
user-invocable: true
metadata:
  {
    "openclaw":
      {
        "emoji": "📝",
        "requires": { "env": ["VEXA_BASE_URL", "VEXA_API_KEY"] },
      },
  }
---

You have access to the `vexa-bridge` MCP tools: `join_meeting`, `get_transcript`,
`bot_status`, `stop_meeting`, `list_meetings`. Use them to run this skill.

## When to use this

Trigger when the user asks you to join, record, note, or summarize an online
meeting — e.g. "note cuộc họp này: <link>", "join this Zoom and take notes",
"summarize the Meet call at 3pm". If the message has no meeting link, ask for
one before doing anything else.

## Steps

1. **Join.** Extract the Google Meet or Zoom URL from the user's message. If
   the user tells you (or it's obvious from context, e.g. they wrote to you
   in Vietnamese) what language the meeting will be in, pass it as
   `language` — pinning the language stops Whisper from re-detecting it
   per segment, which is a major source of both mistranscribed jargon and
   the random-foreign-language hallucinations step 5 filters out. Ask the
   user if it's unclear rather than guessing. Then call
   `join_meeting(meeting_url=<url>, bot_name="Meeting Notetaker", language=<code>)`.
   Keep the `platform` and `native_meeting_id` from the response — you need
   them for every later call.

2. **Confirm.** Tell the user the bot is joining and that they (or someone in
   the call) may need to admit it from the waiting room / lobby. Let them
   know you'll send the summary once the meeting ends.

3. **Wait for the meeting to end.** Vexa has no end-of-meeting webhook, so
   poll instead: every ~2 minutes, call `bot_status()` and check whether this
   meeting's bot is still listed as active. Use your background/cron
   scheduling ability to do this polling rather than blocking synchronously.
   Stop polling once the bot is no longer active, or after a hard cap of
   ~4 hours (then stop it yourself and tell the user the meeting ran long).

4. **Fetch the transcript.** Once the bot is no longer active, call
   `get_transcript(platform, native_meeting_id)`. If it comes back empty,
   wait 30s and retry once — the final transcript can lag slightly behind
   the bot leaving.

5. **Filter ASR noise.** Whisper-based transcription (especially the free
   hosted tier) hallucinates on silence/background noise. Before writing
   the summary or the full transcript, drop any segment that matches any
   of these — they get excluded from the note entirely, not just the
   summary (the original recording is still recoverable via
   `get_transcript` later if ever needed, so nothing is truly lost):
   - Canned outro/filler phrases regardless of language: "thanks for
     watching", "subscribe to the channel", "cảm ơn các bạn đã theo dõi",
     "hãy subscribe cho kênh...", "see you next time", etc.
   - The segment's `language` differs from the meeting's dominant language
     AND the text is short (roughly under ~8 words) AND it doesn't connect
     to what the surrounding segments (same speaker, adjacent timestamps)
     were discussing. A sudden one-off sentence in German/Japanese/Thai/etc.
     in the middle of an otherwise single-language technical discussion is
     almost always noise, not a real language switch.
   - Near-duplicate short phrases repeated verbatim by the same or
     different speakers with no topical connection to the conversation.
   When in doubt, keep the segment — this filter is for obvious noise,
   not for editorializing real content.

6. **Summarize.** From the filtered, speaker-labeled transcript, write a
   summary with this structure:

   ```markdown
   # <meeting name or platform> — <date>

   **Attendees:** <distinct speaker labels found in the transcript>

   ## Key points
   - ...

   ## Decisions
   - ...

   ## Action items
   - [ ] <owner> — <task> (<due date if mentioned>)

   ## Full transcript (from get_transcript, noise filtered)
   **[<start time> - <end time>] <speaker> (<language>):**
   <segment text>
   ```

   Only include a "Decisions" or "Action items" bullet if the transcript
   actually contains one — don't invent items to fill the template. The
   "Full transcript" section lists every remaining segment in order after
   step 5's filter — a clean, readable record of the actual conversation,
   not a raw API dump.

7. **Clean up.** Call `stop_meeting(platform, native_meeting_id)` to make
   sure the bot isn't still holding a seat in the call (safe to call even if
   it already left).

8. **Deliver.** Save the summary to
   `{baseDir}/notes/<YYYY-MM-DD>-<native_meeting_id>.md`, and reply to the
   user in the same chat channel they messaged you from with the summary
   text (not just a "done" — they shouldn't have to open the file to see
   what happened in the meeting).

## Edge cases

- **Bot can't get in** (waiting room, host approval, meeting not started
  yet): tell the user directly instead of retrying silently.
- **User asks to stop early:** call `stop_meeting` immediately, fetch
  whatever transcript exists, and summarize what was captured so far —
  note in the summary that the meeting was cut short.
- **Multiple meetings requested in parallel:** track each by its own
  `(platform, native_meeting_id)` pair; don't mix transcripts across polls.

## Known limitation: transcription accuracy

Testing on real Vietnamese technical meetings (mixed Vietnamese + English
jargon — "button", "popup", "setting", task IDs) found the underlying
Vexa/Whisper transcript itself mistranscribes a meaningful fraction of
domain terms and numbers, independent of anything this skill does at
summarization time — passing `language` at join time (step 1) helps, but
doesn't eliminate it. When telling the user about a completed note, don't
imply the summary is fully accurate — say the key points are best-effort
and point them at the full transcript for anything they need to rely on
precisely (task IDs, exact names, decisions with consequences). If a user
needs materially better accuracy, the real fix is upgrading the STT
backend (a larger self-hosted Whisper model on a GPU box, per
`deploy/transcription` in the Vexa repo) rather than trying to fix it
after the fact in this skill.
