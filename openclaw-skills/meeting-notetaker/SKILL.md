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

1. **Confirm language scope, before joining.** Ask the user what language(s)
   will be spoken in the meeting — a single language, or a mix (e.g.
   "Japanese and Vietnamese"). Don't guess from the user's own chat
   language; the meeting language can be completely different from the
   language they're messaging you in. This matters because it changes both
   how you join (step 2) and how you filter noise later (step 6):
   - **One language confirmed:** pin it at join time for much better
     accuracy.
   - **Multiple languages confirmed (code-switching expected):** do NOT
     pin a single language — forcing Whisper to one language actively
     degrades transcription of the others, since it will try to force
     their audio into that language phonetically instead of transcribing
     it correctly. Record the full set of expected languages instead; it
     feeds step 6's noise filter so real content in a confirmed second
     language isn't mistaken for hallucination.
   - **User doesn't know / can't say:** proceed without pinning a
     language (auto-detect per segment) and tell them accuracy will be
     lower than if they can confirm it later.

2. **Join.** Extract the Google Meet or Zoom URL from the user's message and
   call `join_meeting(meeting_url=<url>, bot_name="Meeting Notetaker", language=<code>)` —
   include `language` only if step 1 confirmed exactly one language; omit
   it otherwise. Keep the `platform` and `native_meeting_id` from the
   response — you need them for every later call.

3. **Notify.** Tell the user the bot is joining and that they (or someone in
   the call) may need to admit it from the waiting room / lobby. Let them
   know you'll send the summary once the meeting ends.

4. **Wait for the meeting to end.** Vexa has no end-of-meeting webhook, so
   poll instead: every ~2 minutes, call `bot_status()` and check whether this
   meeting's bot is still listed as active. Use your background/cron
   scheduling ability to do this polling rather than blocking synchronously.
   Stop polling once the bot is no longer active, or after a hard cap of
   ~4 hours (then stop it yourself and tell the user the meeting ran long).

5. **Fetch the transcript.** Once the bot is no longer active, call
   `get_transcript(platform, native_meeting_id)`. If it comes back empty,
   wait 30s and retry once — the final transcript can lag slightly behind
   the bot leaving.

6. **Filter ASR noise.** Whisper-based transcription (especially the free
   hosted tier) hallucinates on silence/background noise. Before writing
   the summary or the full transcript, drop any segment that matches any
   of these — they get excluded from the note entirely, not just the
   summary (the original recording is still recoverable via
   `get_transcript` later if ever needed, so nothing is truly lost):
   - Canned outro/filler phrases regardless of language: "thanks for
     watching", "subscribe to the channel", "cảm ơn các bạn đã theo dõi",
     "hãy subscribe cho kênh...", "see you next time", etc.
   - The segment's `language` is **outside the set of languages expected
     from step 1** (or outside the transcript's dominant language, if step
     1 landed on "don't know") AND the text is short (roughly under ~8
     words) AND it doesn't connect to what the surrounding segments (same
     speaker, adjacent timestamps) were discussing. A sudden one-off
     sentence in a language nobody said would be in this meeting is almost
     always noise. Critically: if the user confirmed the meeting is, say,
     Japanese *and* Vietnamese, segments tagged `ja` or `vi` are never
     flagged by this rule alone — only a third, unexpected language would
     be. Don't let this rule silently delete a real second language.
   - Near-duplicate short phrases repeated verbatim by the same or
     different speakers with no topical connection to the conversation.
   When in doubt, keep the segment — this filter is for obvious noise,
   not for editorializing real content.

7. **Summarize.** From the filtered, speaker-labeled transcript, write a
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
   step 6's filter — a clean, readable record of the actual conversation,
   not a raw API dump. Also state the confirmed language scope from step 1
   near the top (e.g. "Languages: Japanese, Vietnamese" or "Language:
   not confirmed, auto-detected") so anyone reading the note later knows
   how much to trust it.

8. **Clean up.** Call `stop_meeting(platform, native_meeting_id)` to make
   sure the bot isn't still holding a seat in the call (safe to call even if
   it already left).

9. **Deliver.** Save the summary to
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
summarization time — pinning `language` at join time (step 2, for
single-language meetings) helps, but doesn't eliminate it. Multilingual
meetings (step 1) are inherently lower-accuracy than single-language ones
since no language can be pinned — say so explicitly when handing off the
note. When telling the user about a completed note, don't
imply the summary is fully accurate — say the key points are best-effort
and point them at the full transcript for anything they need to rely on
precisely (task IDs, exact names, decisions with consequences). If a user
needs materially better accuracy, the real fix is upgrading the STT
backend (a larger self-hosted Whisper model on a GPU box, per
`deploy/transcription` in the Vexa repo) rather than trying to fix it
after the fact in this skill.
