# Use full-frame vertical video

## Status

Accepted — 2026-11-15

## Context

On the morning of Nov 15, 2026, clips used a center crop of the 16:9 source to fill the 1080x1920 vertical canvas, cutting off the sides of the stream. I watched a clip and asked why it was getting cropped: it should be the full clip. I then confirmed the rule twice more that evening ("zoomed out so it appears better", then "it should be the full clip"). A cropped Short slipped through the 21:00 hourly slot before the fix landed: https://youtube.com/shorts/k1giCmIZaM8 ("speed is a little chimichum chum"), and it is still live.

## Decision

Every clip shows the full 16:9 source frame: a 1080x1920 vertical canvas, the whole frame scaled to fit the width, and the top and bottom filled with a blurred, darkened copy of the same video. Nothing is cut off the sides. This applies to the queue, the live runner, the VOD batch, and campaign cuts. Already-posted cropped clips stay as-is; they are not re-posted as duplicates.

## Consequences

- Viewers see the whole stream: the room, the phone, the chat context, not just the center.
- The blurred bars are a deliberate look, not a defect.
- The cropped Short k1giCmIZaM8 stays live unless I delete it from YouTube Studio; if I do, the queue entry's `yt_url` must be cleared so the poster re-posts the full-frame version at a later slot.
- Implemented in `cutter.py` (`_cut_segment`): whole frame scaled to 1080 wide (1080x608) centered on a blurred, darkened copy.
- The eligibility gate enforces this for campaign clips: frames at t=5/15/25s are checked for gradient energy in the top, center, and bottom bands, and a center-crop clip fails the framing check.
