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

1. **Language: auto-detect by default — never pin the translation target.**
   The `language` param on join is the **spoken** language of the meeting — NOT
   the language you translate *into*. **Do NOT set it to the translation/target
   language** (e.g. `vi`) just because the live view or summary is in
   Vietnamese. That is the most common mistake here, and pinning the wrong
   spoken language (e.g. `vi` on an English meeting) makes Vexa's downstream
   pipeline drop and garble a lot of the speech.
   - **Default (do this): omit `language`.** The transcriber auto-detects per
     segment and handles English, Vietnamese, and mixed/code-switching meetings
     well. This is the safe choice and what you should do unless told otherwise.
   - **Only pin `language`** if the user EXPLICITLY says the meeting is spoken
     entirely in one specific language AND asks you to pin it. If they name
     more than one spoken language, still omit it (auto-detect). Don't guess the
     spoken language from the user's own chat language.

2. **Join.** Extract the Google Meet or Zoom URL from the user's message and
   call `join_meeting(meeting_url=<url>, bot_name="NexusBot")` — **omit
   `language`** (auto-detect) unless step 1's explicit-pin condition was met.
   Keep the `platform` and `native_meeting_id` from the
   response — you need them for every later call. The response also includes a
   `share_link` field when the live-translate web app is configured (env
   `WEB_PUBLIC_URL` on the vexa-bridge server) — this is the URL to the
   realtime transcript + translation room for this meeting.

3. **Post the live-view link — REQUIRED. This is the whole point of the skill;
   never skip or paraphrase it away.** The `join_meeting` response contains a
   `share_link` field, e.g.
   `http://192.168.4.15:8080/meet/google_meet/abc-defg-hij?lang=vi`. Your reply
   in the Slack thread **MUST contain that exact `share_link` URL as its own
   clickable link.** It is the live transcript + translation page for everyone
   to watch together. It is a **different URL from the Google Meet link**, and
   the Meet link is **NOT** an acceptable substitute — a reply that shows only
   the Meet URL is a failure. Reply in this shape (replace `<share_link>` with
   the real value from the response):

   ```
   🎙️ NexusBot đang vào phòng họp (có thể cần admit nó khỏi phòng chờ).
   📺 Xem transcript + bản dịch trực tiếp (tiếng Việt): <share_link>
   ```

   The target language is fixed by the link (viewers can't change it), by
   design. Also let them know you'll send the full summary when the meeting
   ends. Only if `share_link` is genuinely empty/missing (web app not
   configured) may you omit it and say so — never fabricate a URL.

4. **Wait for the meeting to end.** Vexa has no end-of-meeting webhook, so
   poll instead: every ~2 minutes, call `bot_status()` and check whether this
   meeting's bot is still listed as active. Use your background/cron
   scheduling ability to do this polling rather than blocking synchronously.
   Stop polling once the bot is no longer active, or after a hard cap of
   ~4 hours (then stop it yourself and tell the user the meeting ran long).

   On each poll where the bot is still `active`, also call `get_transcript`
   and compare the segment count/last segment timestamp to the previous
   poll. Vexa's bot does not reliably notice when it's alone in an empty
   room — if **3 consecutive polls (~6 minutes)** show no new segments,
   treat that as everyone having left: call `stop_meeting` yourself, treat
   the meeting as ended, and proceed to steps 5-8 as normal. Then, before
   step 9's delivery, ask the user to confirm they still want the
   summary sent (the "meeting ended" call is a heuristic, not a certainty
   — a long silent stretch during a real, ongoing meeting is possible) —
   send it only after they say yes.

5. **Fetch the transcript.** Once the bot is no longer active, call
   `get_transcript(platform, native_meeting_id)`. If it comes back empty,
   wait 30s and retry once — the final transcript can lag slightly behind
   the bot leaving. Also call `stop_meeting(platform, native_meeting_id)`
   right here (safe even if it already left) — don't hold the bot's seat
   while steps 6-8 run, since step 7 may need to wait on a reply. Delegate
   step 6 (dedup/noise-filter/context-correct, plus flagging gaps for step
   7) to a sub-agent using the **Haiku** model rather than doing it inline
   yourself — give it the raw segments plus step 6's exact instructions
   below, and have it return the filtered transcript and the gap list
   together. This matters even for short transcripts (Haiku is the
   intended model for this analysis work), not just to manage context size
   on long ones. Once step 7 is resolved (an answer arrives, or times
   out), delegate step 8 (drafting the summary prose) to a sub-agent the
   same way, giving it the filtered transcript plus whatever step 7
   answers you got.

6. **Filter ASR noise.** ASR transcription can still hallucinate on silence
   or background noise. Before writing
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

   Separately from dropping noise, **correct** (don't drop) segments where
   a technical term or English loanword was clearly mis-transcribed
   phonetically — e.g. "lock time" transcribed instead of "log time", or
   "tạo tab" instead of "tạo task" — when the surrounding context makes the
   intended word unambiguous (a Jira-integration discussion saying "tạo
   tab...hay là agile" almost certainly meant "tạo task"). Keep a list of
   every correction made (original → corrected, with timestamp) and print
   it as a note near the top of the summary, the same way you'd disclose
   any other edit to the source material — don't silently rewrite the
   transcript. When you're not confident, leave the original text as-is
   rather than guessing — but don't just leave it silently either: hand it
   to step 7 as a gap candidate instead.

7. **Identify gaps and confirm with the meeting caller.** From the filtered
   transcript, flag points where something is unclear, ambiguous, or
   missing badly enough that guessing wrong would change the note,
   key points, decisions, or action items:
   - A decision or action item is mentioned but its owner, scope, or due
     date is unstated or ambiguous.
   - A segment is garbled or incoherent enough that its meaning can't be
     inferred from surrounding context (unlike step 6's confident
     corrections).
   - A step 6 correction candidate you weren't confident enough to
     auto-apply.
   - A topic is clearly being discussed and then the transcript jumps
     (a timestamp gap, or an abrupt subject change with no resolution),
     suggesting lost audio, with no way to tell how it concluded.
   - A named reference (a document, ticket ID, number, person) is
     mistranscribed or cut off in a way that could change an action
     item's meaning.

   If nothing rises to this bar, skip this step entirely and go straight
   to step 8 — don't manufacture questions to pad a list. Only raise real
   gaps that would actually change the output.

   If there are gaps, reply in the same channel/thread the user invoked
   you from, addressed to the person who asked you to join this meeting,
   with a numbered list of concrete questions, e.g.:

   ```
   📝 Trước khi tổng hợp note, mình cần xác nhận vài điểm bot nghe chưa rõ / thiếu transcript:
   1. ...
   2. ...
   Bạn confirm/bổ sung giúp mình để note được chính xác nhé.
   ```

   Then wait for their reply in that thread before moving to step 8 — this
   is a real dependency, not a fire-and-forget notice. If there's no reply
   after a reasonable wait (~15-20 minutes — poll/schedule it the same way
   step 4 does), proceed to step 8 on the best-effort transcript, but
   explicitly mark the still-unresolved points in the summary (e.g. "chưa
   được xác nhận") instead of silently guessing or waiting forever.

   Fold whatever they confirm into the context you hand to step 8 — use it
   to fill the gap, resolve the ambiguous correction, or fix the action
   item's owner/date. Weave it into the relevant section rather than
   appending their raw reply as a separate block.

8. **Summarize.** From the filtered, speaker-labeled transcript — plus any
   step 7 confirmations — write a summary with this structure:

   ```markdown
   # <meeting name or platform> — <date>

   **Attendees:** <distinct speaker labels found in the transcript>

   ## Key points
   - **<key point 1>**
   - **<key point 2>**

   ## Decisions
   - ...

   ## Action items
   - [ ] <span style="color:green"><owner> — <task> (<due date if mentioned>)</span>

   _<any step 6 corrections: "original" → "corrected" (timestamp), one per line — omit this note entirely if there were none>_

   ## Full transcript (from get_transcript, noise filtered)
   **[<start time> - <end time>] <speaker> (<language>):**
   <segment text>
   ```

   Bold every "Key points" bullet in full (`**...**`) and color every
   "Action items" bullet's owner/task/date text green via
   `<span style="color:green">...</span>` — keep the `- [ ]` checkbox
   syntax itself outside the span so it still renders as a checkbox.
   Only include a "Decisions" or "Action items" bullet if the transcript
   actually contains one — don't invent items to fill the template.

   **Pay special attention to the closing of the meeting.** People usually
   recap the discussion and spell out next-actions in the last stretch of a
   call — phrases like "tóm lại...", "vậy chốt là...", "việc tiếp theo...",
   "để mình tổng hợp lại...", "so to summarize...", "action items are...",
   "let's make sure X does Y by...". Treat the final ~15% of the transcript
   (and any segment that opens with a recap/next-step cue like the above) as
   the highest-signal source for both "Key points" and "Action items":
   - When a closing recap conflicts with something said earlier, trust the
     recap — it's the speakers' own confirmed conclusion.
   - Any task or owner assigned during the wrap-up almost always belongs in
     "Action items", even if it was only mentioned once. Prefer the owner and
     due date as stated in the recap over an earlier, vaguer mention.
   - If the meeting ends with an explicit spoken summary, its points should
     map onto your "Key points"/"Decisions" — don't bury a conclusion the
     participants themselves highlighted.
   This is a weighting hint, not a scope limit: still capture key points and
   action items raised anywhere in the meeting, and still don't invent items
   that were never actually said.

   The
   "Full transcript" section lists every remaining segment in order after
   step 6's filter — a clean, readable record of the actual conversation,
   not a raw API dump. Also state the confirmed language scope from step 1
   near the top (e.g. "Languages: Japanese, Vietnamese" or "Language:
   not confirmed, auto-detected") so anyone reading the note later knows
   how much to trust it.

9. **Deliver.** Save the summary to
   `{baseDir}/notes/<YYYY-MM-DD>-<native_meeting_id>.md`. If the meeting
   ended normally (bot left, or you stopped it on the user's explicit
   request), reply immediately in the same chat channel they messaged you
   from with the summary text (not just a "done" — they shouldn't have to
   open the file to see what happened in the meeting). If the meeting was
   ended by the step 4 empty-room heuristic, ask first — e.g. "Cuộc họp có
   vẻ đã kết thúc (không có ai nói suốt 6 phút) — gửi kết quả tổng hợp cho
   bạn nhé?" — and only send the summary after they confirm. `stop_meeting`
   was already called back in step 5, so there's nothing left to clean up
   here.

## Edge cases

- **Bot can't get in** (waiting room, host approval, meeting not started
  yet): tell the user directly instead of retrying silently.
- **User asks to stop early:** call `stop_meeting` immediately, fetch
  whatever transcript exists, and summarize what was captured so far —
  note in the summary that the meeting was cut short.
- **Multiple meetings requested in parallel:** track each by its own
  `(platform, native_meeting_id)` pair; don't mix transcripts across polls.
- **Everyone else leaves the meeting:** see step 4's silence heuristic —
  auto-stop the bot, but confirm with the user before delivering (step 9)
  since it's a heuristic, not a certainty.
- **No reply to step 7's gap-confirmation questions:** don't block
  delivery forever — after the ~15-20 minute wait, draft the summary from
  the best-effort transcript and mark the unresolved points explicitly
  instead of guessing.

## Known limitation: transcription accuracy

Transcription runs through [`soniox-bridge`](../../services/soniox-bridge/)
(Soniox's real-time API), which replaced an earlier self-hosted Whisper
attempt after it repeatedly crashed the host under CPU/memory load — Soniox
needs no local model and tested cleanly on real English and Vietnamese
speech. `get_transcript` (step 5) reads exclusively from the B-full
continuous per-speaker Soniox stream, via `live-translate` — Vexa's own
confirm-layer transcript is never used, since it drops text at ~30s turn
seams. Even so, when telling the user about a completed note, don't imply
the summary is fully accurate — say the key points are best-effort and point
them at the full transcript for anything they need to rely on precisely
(task IDs, exact names, decisions with consequences). See
[`soniox-bridge/README.md`](../../services/soniox-bridge/README.md#known-limitations)
for the specific gaps (single dominant language per chunk, no diarization
from the STT call itself, approximate confidence mapping).
