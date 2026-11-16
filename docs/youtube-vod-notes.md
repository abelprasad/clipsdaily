# YouTube VOD mode — notes for when live mode is done (Abel: live first, YouTube after)

## Source reel: Oliver Merrick, "THE CLIP MACHINE" (reel DbVKVz0y8xo, Jul 28, 2026)
- Editing is the easy part. Choosing the moment is the hard part.
- Build a SELECTION layer first, before the cutter.

## Selection method to use for youtube_vod.py
1. Scrape the latest 100 clips from the biggest podcast / long-form short-form accounts (e.g. Steven Bartlett, Chris Williamson, Alex Hormozi) — capture views, post date, duration, transcript, text overlay, format.
2. Pull the original long-form episodes' complete transcripts WITH timestamps. Timestamps are non-negotiable — they let you match every clip back to the exact episode and exact moment.
3. Reverse engineer each winning clip: why those ~47 seconds, where it starts, what context got removed, whether the payoff moved forward, spoken hook, text overlay, format, performance vs that account's normal clips.
4. Turn the patterns into selection rules, then hand any new timestamped transcript to the selector — it returns strongest moments, exact timestamps, hook options, text overlays, formats, editing instructions.
5. Tools named in the reel: Remotion (programmatic editing), Apify (scraping), Airtable (MOMENTS store), Claude (matching/analysis).

## Do NOT build this yet
- Live Twitch/Kick/YouTube Live mode comes first, complete and tested.
- youtube_vod.py is manual-trigger (`youtube_vod.py <url>`) at first, auto mode only if Abel approves a channel list later.
