# Kick monitoring — status, route, limits

## Status (verified Nov 16, 2026)

Kick monitoring was already built Nov 15, 2026 and is live. Monitored
right now: `kick/xqc` and `kick/adinross` (in `config.yaml`, 10 watches
total; the live runner started Nov 16 10:45 watches both). No Kick
developer account, no credentials, no cost, nothing to buy.

Proof it works end to end:
- Adin Ross, Nov 16 04:27: Kick chat spike detected (141 msgs in 10s,
  median 26, intensity 5.42) → clip cut 05:56: `kick_adinross_72s.mp4`
  (30s, 1080x1920) + 75s TikTok version, real transcript, frame-checked.
- xQc, Nov 16: Pusher chat connection held 60s idle with no errors
  (offline at test time, so no messages — expected).
- Channel checks via the public Kick API, Nov 16: xqc 1,655,134
  followers, adinross 3,110,526 followers, both verified.

## Route (simplest reliable one; mirrors Twitch)

- Live check + recording: `streamlink` resolves `https://kick.com/<channel>`
  (public HLS, no account). Same `recorder.py` as Twitch.
- Chat: public Kick API `GET kick.com/api/v2/channels/<slug>` (no auth)
  resolves channel id → chatroom id; then per-channel realtime config
  `POST web.kick.com/api/v1/realtime/channels/<id>/chat/connection`
  (no auth) returns a fresh Pusher app key + cluster; subscribe to
  `chatrooms.<id>.v2` and count `ChatMessageEvent`. Same `SpikeTracker`
  as Twitch (3x median, min 20 msgs/10s window, 5-min shared cooldown
  keyed by streamer name, so xqc on Twitch + Kick never double-clips).
- Downstream is identical: cutter (full-frame, hook, captions), poster
  (platform passed through; clip credit reads `kick_<channel>`).

## What Kick cannot do that Twitch can

- **No VOD backfill.** Kick has no public VOD download API, so there is
  no Kick throwback queue. The hourly queue stays Twitch-VOD-only;
  Kick clips come from live streams only.
- **Chat rides unofficial endpoints.** The official API
  (`api.kick.com/public/v1`, docs.kick.com) needs an OAuth developer app
  + PKCE and covers channels, livestreams, and webhooks
  (`chat.message.sent`, `livestream.status.updated`) — but not chat
  history or VODs. The current route uses Kick's own website endpoints
  (`api/v2`, `web.kick.com` realtime config) with no auth, which is why
  no app was created. Precedent for breakage: the old hardcoded Pusher
  key died Oct 2026 (4001 "not in this cluster"); the per-channel
  config is the working route, but Kick can change it without notice.
- **Smaller chats, rarer spikes.** Same 20-msg floor as Twitch; Kick
  chats are smaller, so spikes fire less often per hour live.
- **No clips API.** There is no Kick equivalent of Twitch clips to
  fetch after the fact; capture-while-live is the only source.

## Lost-clip rescue (added Nov 16, 2026)

`runner.stage_to_queue()`: a live clip that posts to ZERO platforms is
staged at the FRONT of `queue/queue.json` (id `live-<platform>-<channel>-<N>s`,
`source: "live"`, `campaign_eligible: false`) so the hourly poster
retries it next slot instead of losing it. This is the hole that ate the
overnight adinross clip (cut 05:56, TikTok broken + YouTube capped, never
staged, never retried). Partial posts are NOT staged — the staged entry
starts with `yt_url`/`tt_url` unset and the hourly poster would re-post
a platform that already went live (duplicate Short). Dedup by id.
Tests: `test_live_staging.py` 4/4 (staging shape, dedup, Twitch
staging, campaign gate blocks a staged live entry).

## Campaign safety

A staged live entry has no `campaign_id` and no `vod_id`.
`auto_submit.write_job` requires a `campaign_id`, and
`eligibility_gate` requires `clip.vod_id == campaign.vod_id` — so a
Kick (or any live) clip can never become a campaign submission. Verified
by test 4 in `test_live_staging.py`. Campaigns stay Speed-Twitch-VOD-only
by construction.

## Enable / disable

The `streamers` list in `config.yaml` is the switch: remove the `kick`
entries to stop Kick, add a verified channel to start it. There is no
separate `kick:` flag — a default-off flag would have disabled the
already-working path. Takes effect on the next runner restart (the
runner reads config once at startup; the hourly poster needs no restart).

## Checked and NOT added (Nov 16, 2026)

- stableronaldo: verified Kick channel, 24,164 followers — but
  `recent_categories: []`, no VODs, no sign of recent Kick streaming.
- clix: verified, 26,714 followers — same, dormant on Kick.
- kaicenat (1,317), ishowspeed (3,118), sykkuno (407), jynxzi (341),
  hasanabi (4,707): placeholder channels, not their real presence.
- zackrawrr (3,593): exists, dormant. drake (661,495): real but
  intermittent — already dropped from the watch list Nov 15.

## Known gaps (not fixed here)

- **No runner auto-restart.** The Nov 15 19:27 runner instance's log
  ends 22:01; the next start was Nov 16 10:45. The overnight Kick clip
  was cut during that window by a runner whose stdout was never logged,
  and its post was lost to the lost-clip hole (now fixed for future
  clips). If the runner dies again, monitoring stops until someone
  restarts it — a watchdog/cron restart is still open.
- **Recovered adinross clip, unposted.** `clips/kick_adinross_72s.mp4` +
  75s TikTok version (Nov 16 05:56) were NOT staged into the live queue
  — staging it would post it at the next hourly slot, and no post goes
  out without my go. Cleanup deletes unposted clips after 48h
  (~Nov 18 05:58). My call: stage it (posts next slot) or let it lapse.

## ToS / rate-limit notes

- All Kick reads are public, no-login endpoints (same posture as
  anonymous Twitch IRC): no account, no token, nothing written to Kick.
  Streamlink resolves public HLS; the Pusher route is the same realtime
  config endpoint kick.com's own frontend uses.
- Risk: Kick can change or rate-limit the undocumented website endpoints
  without notice (Oct 2026 key death is the precedent). The official
  API's numeric rate limits are unpublished. Current load is light:
  ~1 streamlink live-check/min per channel + 1 Pusher connection per
  live stream. If the Pusher route breaks, the fallback is the official
  API with a developer app (needs my Kick login) + webhooks — not
  built, not needed today.
