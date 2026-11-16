#!/bin/bash
# Half-hour Instagram poster for clipsdaily. Run by cron at :05 and :35.
# Posts the most recently staged Reel in indra's ig-outbox (status "staged",
# ig_slot within the last 60 min). Exits quietly (0) when nothing is staged.
set -u
OUTBOX_BASE="/home/abel/clipsdaily/ig-outbox"
WORKDIR="$HOME/workspace/clipsdaily-build/ig-hourly"
mkdir -p "$WORKDIR"

# Restore the indra SSH helper if /tmp was wiped (see AGENTS.md).
if [ ! -x /tmp/indra.sh ]; then
  cp "$HOME/workspace/ssh-tail-proxy.py" /tmp/ssh-tail-proxy.py 2>/dev/null
  chmod 600 /tmp/ssh-tail-proxy.py 2>/dev/null
  printf '#!/bin/bash\nexec ssh -o UserKnownHostsFile=/home/hatch/.ssh/known_hosts -i /home/hatch/.ssh/id_ed25519 -o ProxyCommand="python3 /tmp/ssh-tail-proxy.py %%h %%p" friday@100.78.151.90 "$@"\n' > /tmp/indra.sh
  chmod 700 /tmp/indra.sh
fi
[ -x /tmp/indra.sh ] || exit 0

NOW_EPOCH=$(date +%s)
CLIP_ID=""
BEST_AGE=999999
for d in $(/tmp/indra.sh "ls $OUTBOX_BASE 2>/dev/null"); do
  m="$OUTBOX_BASE/$d/meta.json"
  STATUS=$(/tmp/indra.sh "grep -o '\"status\": *\"[a-z]*\"' $m 2>/dev/null | head -1")
  echo "$STATUS" | grep -q '"staged"' || continue
  SLOT=$(/tmp/indra.sh "grep -o '\"ig_slot\": *\"[^\"]*\"' $m 2>/dev/null | head -1 | sed 's/.*\"\(....-..-..T..:..\)\".*/\1/'")
  [ -n "$SLOT" ] || continue
  SLOT_EPOCH=$(date -d "$SLOT" +%s 2>/dev/null) || continue
  AGE=$((NOW_EPOCH - SLOT_EPOCH))
  if [ "$AGE" -ge -300 ] && [ "$AGE" -le 3600 ] && [ "$AGE" -lt "$BEST_AGE" ]; then BEST_AGE=$AGE; CLIP_ID=$d; fi
done
[ -n "$CLIP_ID" ] || exit 0

DIR="$OUTBOX_BASE/$CLIP_ID"
VIDEO="$(/tmp/indra.sh "ls $DIR/*.mp4 2>/dev/null | head -1")"
[ -n "$VIDEO" ] || exit 0
/tmp/indra.sh "sudo -n -u abel cat '$VIDEO'" > "$WORKDIR/clip.mp4" || exit 0
/tmp/indra.sh "sudo -n -u abel cat $DIR/caption.txt" > "$WORKDIR/caption.txt" 2>/dev/null || echo "" > "$WORKDIR/caption.txt"
ffmpeg -y -v error -ss 1 -i "$WORKDIR/clip.mp4" -vframes 1 -q:v 3 "$WORKDIR/cover.jpg" 2>/dev/null
CAPTION="$(cat "$WORKDIR/caption.txt")"

# Post to Instagram (@clippedaily31, account 17841427153900705).
OUT="$(instagram-cli post-feed --account-id 17841427153900705 --file "$WORKDIR/clip.mp4" --cover "$WORKDIR/cover.jpg" --caption "$CAPTION" 2>&1)"
echo "$OUT" | grep -q "media_fbid" || { echo "IG post failed for $CLIP_ID: $OUT" >&2; exit 1; }
MEDIA_FBID="$(echo "$OUT" | sed -n 's/.*"media_fbid":"\([0-9]*\)".*/\1/p')"

# Mark posted on indra so it is never posted twice.
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
/tmp/indra.sh "sudo -n -u abel tee $DIR/.posted >/dev/null" <<EOF
{"status":"posted","media_fbid":"$MEDIA_FBID","posted_at_utc":"$TS"}
EOF
# Also flip meta.json status if present.
/tmp/indra.sh "sudo -n -u abel sed -i 's/\"status\": *\"staged\"/\"status\": \"posted\"/' $DIR/meta.json 2>/dev/null; true"
echo "Posted $CLIP_ID to IG as $MEDIA_FBID at $TS"
