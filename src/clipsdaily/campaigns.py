"""Shared campaign schema + helpers for clipsdaily monetization automation.

A campaign record (campaigns.json) is the single source of truth for
every campaign the watcher finds. Fields:

  id                 Content Rewards UUID, or "vyro:<id>" for Vyro.
  source             "content_rewards" | "vyro"
  title, brand, category
  streamer           watchlist channel (lowercase), or null if unmatched
  status             "active" | "ended" | "unknown"   (from the site)
  state              "discovered" | "join_requested" | "joined"
                     | "skipped" | "needs_review" | "ended"
                     (our workflow state — the watcher never overwrites
                     "joined" once set; a human/parent marks it)
  state_reason       why the campaign is in this state
  rate_per_1k        dollars per 1,000 views (min across platforms)
  min_payout_cents / max_payout_cents   per clip per platform
  min_views          views needed to reach min payout (derived)
  budget_total_cents / budget_spent_cents / budget_available_cents
  platforms          ["instagram","tiktok","youtube"] subset
  requires_application  bool — true means a human must apply
  is_verified        bool
  url                campaign page URL
  window_text        raw footage-window sentence from the campaign page
  window_start_s     int seconds from VOD start, or None if unparsed
  window_end_s       int seconds, or None = end of stream/VOD
  vod_id             Twitch VOD id for the eligible stream (null until
                     resolved — campaign_cut refuses to run without it)
  vod_date           "YYYY-MM-DD" of the eligible stream
  stream_date_text   e.g. "Stream 11.6.26" (as the campaign states it)
  required_mentions  list of strings every caption must contain
  required_hashtag   e.g. "#IShowSpeed" (case-insensitive match)
  caption_must_name  per-clip value that must appear in the caption
                     (e.g. the prize destination "Japan"/"Hong Kong")
  exclude_ranges     [[start_s, end_s], ...] VOD ranges to never clip
                     (e.g. stream-ending spikes with no campaign content)
  moments            optional curated [{spike_s, destination, hook}]
  hook_by_destination optional {destination: hook line}
  local_video        optional local video file covering the window
  local_video_offset_s  VOD seconds at the start of local_video
  discovered_at / updated_at   ISO timestamps
  raw                raw discover/detail record (kept for audit)

Join rules (ALL must hold for auto-join; any failure is logged):
  1. status == "active"
  2. budget_available_cents > 0
  3. rate_per_1k >= 1.0
  4. requires_application == False
  5. streamer is on the watchlist (matched in title/description)
  6. window_start_s is not None (explicit footage window parsed)
  7. platforms intersect {youtube, tiktok, instagram} is non-empty
Failure of 5 alone -> "needs_review" (a VOD might still be obtainable,
but a human decides). Any other failure -> "skipped" with reason.
"""
import json
import re
from pathlib import Path

from .paths import runtime_home
HERE = runtime_home()
CAMPAIGNS_FILE = HERE / "campaigns.json"
JOIN_REQUESTS_FILE = HERE / "join_requests.json"
JOIN_RESULTS_FILE = HERE / "join_results.json"

MIN_RATE_PER_1K = 1.0
PLATFORMS = {"youtube", "tiktok", "instagram"}

_TS_RE = re.compile(r"(\d+):(\d{2})(?::(\d{2}))?")


def parse_hms(text):
    """'2:56:29' -> 10589, '56:29' -> 3389, '90' -> 90. None if no match."""
    m = _TS_RE.search(str(text))
    if not m:
        return None
    if m.group(3) is not None:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    return int(m.group(1)) * 60 + int(m.group(2))


# "from 2:56:29 until the end", "from 2:56:29 to end of stream",
# "footage from 2:56:29 - 3:04:09", "only 2:56:29 to the end is OK".
_WINDOW_RES = [
    re.compile(r"from\s+(\d+:\d{2}(?::\d{2})?)\s+(?:until|to|through|-)\s+"
               r"(the\s+end(?:\s+of\s+(?:the\s+)?stream)?|end\s+of\s+stream|"
               r"\d+:\d{2}(?::\d{2})?)", re.I),
    re.compile(r"(\d+:\d{2}(?::\d{2})?)\s*[-–]\s*"
               r"(the\s+end|end|\d+:\d{2}(?::\d{2})?)", re.I),
    re.compile(r"(?:starting|after|beginning)\s+(?:at\s+)?"
               r"(\d+:\d{2}(?::\d{2})?)", re.I),
]


def parse_window(text):
    """Parse a footage-window sentence into (start_s, end_s|None).

    Returns (None, None) when no explicit window can be stated — the
    caller must treat that as NOT JOINABLE. Never guess a window.
    """
    if not text:
        return None, None
    for rx in _WINDOW_RES:
        m = rx.search(text)
        if m:
            start = parse_hms(m.group(1))
            end_raw = m.group(2).strip()
            if re.match(r"(?i)the\s+end|end$", end_raw):
                return start, None
            return start, parse_hms(end_raw)
    return None, None


def load_campaigns(path=CAMPAIGNS_FILE):
    if not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_text())
    except Exception:
        return {}
    if isinstance(data, dict):
        return data.get("campaigns", data)
    return {}


def save_campaigns(campaigns, path=CAMPAIGNS_FILE):
    path = Path(path)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"campaigns": campaigns}, indent=2))
    tmp.replace(path)


def load_watchlist(config_path=None):
    """Watchlist streamers from config.yaml (regex parse, no yaml dep)."""
    path = Path(config_path or HERE / "config.yaml")
    channels = []
    try:
        for line in path.read_text().splitlines():
            m = re.match(r"\s*channel:\s*([A-Za-z0-9_]+)", line)
            if m:
                channels.append(m.group(1).lower())
    except Exception:
        pass
    return channels


def match_streamer(title, description, watchlist):
    """First watchlist streamer named in title/description, or None."""
    hay = ("%s\n%s" % (title or "", description or "")).lower()
    for ch in watchlist:
        if re.search(r"\b%s\b" % re.escape(ch), hay):
            return ch
    return None


def evaluate_join_rules(rec, watchlist):
    """Return (decision, reason). decision in join/skip/needs_review.

    rec is a normalized campaign record. Never auto-joins when the
    footage window cannot be stated exactly.
    """
    if rec.get("status") not in ("active", None):
        return "skip", "status=%s (not active)" % rec.get("status")
    avail = rec.get("budget_available_cents")
    if avail is not None and avail <= 0:
        return "skip", "budget exhausted (available=%s)" % avail
    rate = rec.get("rate_per_1k")
    if rate is None or rate < MIN_RATE_PER_1K:
        return "skip", "rate $%s/1K below $%s floor" % (rate, MIN_RATE_PER_1K)
    if rec.get("requires_application"):
        return "needs_review", "requires application (human must apply)"
    streamer = rec.get("streamer")
    if not streamer:
        return "needs_review", "no watchlist streamer named in title/description"
    if streamer not in [w.lower() for w in watchlist]:
        return "needs_review", "streamer %s not on watchlist" % streamer
    if rec.get("window_start_s") is None:
        return "skip", "no explicit footage window stated"
    plats = set(rec.get("platforms") or [])
    if not (plats & PLATFORMS):
        return "skip", "no usable platforms %s" % sorted(plats)
    return "join", "all rules pass"


def normalize_discover_record(raw):
    """Normalize one Content Rewards discover record (embedded JSON)."""
    cid = raw.get("id")
    rate_label = str(raw.get("ratePer1kLabel") or "")
    m = re.search(r"([\d.]+)", rate_label.replace(",", ""))
    rate = float(m.group(1)) if m else None
    # ratePer1kLabel may be a range like "$1–$1.50": take the low end.
    total = raw.get("budgetTotalRaw")
    spent = raw.get("budgetSpentRaw")
    avail = raw.get("availableBudgetRaw")
    if avail is None and total is not None and spent is not None:
        avail = total - spent
    desc = raw.get("description") or ""
    w_start, w_end = parse_window(desc)
    rec = {
        "id": cid,
        "source": "content_rewards",
        "title": raw.get("title") or raw.get("name") or "",
        "brand": raw.get("brand") or "",
        "category": raw.get("category") or "",
        "streamer": None,
        "status": "active" if (avail is None or avail > 0) else "ended",
        "state": "discovered",
        "state_reason": "",
        "rate_per_1k": rate,
        "min_payout_cents": None,
        "max_payout_cents": None,
        "min_views": None,
        "budget_total_cents": (int(total * 100)
                               if isinstance(total, (int, float)) else None),
        "budget_spent_cents": (int(spent * 100)
                               if isinstance(spent, (int, float)) else None),
        "budget_available_cents": (int(avail * 100)
                                   if isinstance(avail, (int, float))
                                   else None),
        "platforms": list(raw.get("platforms") or []),
        "requires_application": bool(raw.get("requiresApplication")),
        "is_verified": bool(raw.get("isVerified")),
        "url": ("https://contentrewards.com/c/campaigns/%s" % cid
                if cid else None),
        "window_text": desc,
        "window_start_s": w_start,
        "window_end_s": w_end,
        "vod_id": None,
        "vod_date": None,
        "stream_date_text": None,
        "required_mentions": [],
        "required_hashtag": None,
        "caption_must_name": None,
        "exclude_ranges": [],
        "moments": [],
        "hook_by_destination": {},
        "local_video": None,
        "local_video_offset_s": None,
        "discovered_at": None,
        "updated_at": None,
        "raw": raw,
    }
    return rec


def enrich_from_detail(rec, detail):
    """Fill payout/window/status fields from a detail-page record."""
    payouts = detail.get("payouts") or []
    if not payouts:
        cfg = detail.get("configuration") or {}
        payouts = cfg.get("payoutModel") or []
    rates, mins, maxs = [], [], []
    for p in payouts:
        rate = p.get("rateCents", p.get("rate"))
        if rate is not None:
            rates.append(rate)
        mn = p.get("minPayoutCents", p.get("minPayout"))
        mx = p.get("maxPayoutCents", p.get("maxPayout"))
        if mn is not None:
            mins.append(mn)
        if mx is not None:
            maxs.append(mx)
    if rates:
        rec["rate_per_1k"] = min(rates) / 100.0
    if mins:
        rec["min_payout_cents"] = min(mins)
    if maxs:
        rec["max_payout_cents"] = max(maxs)
    if rec.get("min_payout_cents") and rec.get("rate_per_1k"):
        rate_cents = rec["rate_per_1k"] * 100.0
        if rate_cents > 0:
            rec["min_views"] = int(rec["min_payout_cents"] / rate_cents * 1000)
    if detail.get("status"):
        rec["status"] = detail["status"]
    if detail.get("description"):
        rec["window_text"] = detail["description"]
        w_start, w_end = parse_window(detail["description"])
        if w_start is not None:
            rec["window_start_s"] = w_start
            rec["window_end_s"] = w_end
    if detail.get("budgetCents") is not None:
        rec["budget_total_cents"] = detail["budgetCents"]
    metrics = detail.get("metrics") or {}
    if metrics.get("budgetSpentCents") is not None:
        rec["budget_spent_cents"] = metrics["budgetSpentCents"]
        if rec.get("budget_total_cents") is not None:
            rec["budget_available_cents"] = (
                rec["budget_total_cents"] - metrics["budgetSpentCents"])
    if detail.get("requiresApplication") is not None:
        rec["requires_application"] = bool(detail["requiresApplication"])
    if detail.get("platforms"):
        rec["platforms"] = list(detail["platforms"])
    return rec
