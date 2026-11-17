# Content Rewards browser automation — ClipForge (OPT-IN)

This module (`src/clipsdaily/contentrewards.py`, Playwright) replaces the
three Friday/browser touchpoints of the money loop with on-box automation:

| Command | Replaces | What it does |
|---|---|---|
| `contentrewards auth` | Manual login | Guided headed login; saves only the Playwright storage state |
| `contentrewards join` | Friday clicks Join | Clicks Join per `join_requests.json`, verifies the green Joined badge, appends `join_results.json` |
| `contentrewards submit` | Friday browser submit | Submits pending `submit-outbox/` jobs, verifies the dashboard shows Pending WITH a submission ID, marks submitted |
| `contentrewards earnings-dump` | Friday dashboard dump | Scrapes the submissions dashboard to `earnings_dump.json` (then run `earnings.py --update`) |

Standalone usage (the `clipforge` CLI wires these in later):

```
python3 -m clipsdaily.contentrewards auth
python3 -m clipsdaily.contentrewards join [--dry-run]
python3 -m clipsdaily.contentrewards submit [--dry-run]
python3 -m clipsdaily.contentrewards earnings-dump [--dry-run]
```

Global flags: `--home <runtime-home>` (default `$CLIPSDAILY_HOME` else
cwd), `--base-url <url>` (default `https://contentrewards.com`),
`--dry-run` (plan only — parses jobs, runs gates, prints what WOULD
happen; touches no remote site, writes nothing, opens no browser).

## Opt-in flag

Default is **OFF**. Nothing in this module posts, joins, or submits
anything unless `config.yaml` in the runtime home contains:

```yaml
campaign_automation: true
```

With the flag absent, false, or the config unreadable, every command
(including `auth`) refuses with exit code 2 and changes nothing. The
flag is re-read on every run, so flipping `config.yaml` takes effect
without a restart.

## The one-strike rule

**Content Rewards bans an account from EVERY campaign permanently for
a single bad submission.** There is no appeal path in the design. This
module is built paranoid, and it fails CLOSED on every path:

- **Gate re-run before every submit.** `eligibility_gate.gate_clip`
  runs on the clip + campaign for each job, at submit time, not just at
  queue time. Any failure (window, caption, framing) or anything
  unverifiable = mark failed, never submit. Borderline = blocked.
- **30-minute window.** A job whose `posted_at` is more than 30 minutes
  old is never submitted late. (The outbox's own `--list-pending`
  expiry marks it `expired` first; the module also checks the window
  itself before touching the browser.)
- **Join badge verification.** A join is recorded as `joined` only when
  the green Joined badge is visibly present after clicking Join. No
  badge = `failed` with a reason. A join is never claimed on faith.
- **Submission-ID verification.** A submit counts only when the
  submissions dashboard shows the clip as Pending **with a submission
  ID**. On-page confirmation alone is not enough. No ID = mark failed.
- **Never double-submit.** A submitted job is done. Before filing, the
  module checks the dashboard for an existing row for the clip URL; if
  one is there, it marks the job submitted with that ID instead of
  filing again.
- **Any doubt = do nothing to the remote site.** Record `failed` with
  the reason, move on to the next job. A failed job stays failed until
  a human looks at it; it is retried only while still inside its
  30-minute window (a pending job left by an interrupted run is picked
  up by the next run, and the dashboard pre-check prevents a duplicate
  if the first attempt actually went through but marking failed).
- **No session = no run.** All three commands require the session file
  (below). A missing or empty session refuses with exit code 2.
- **No password is ever stored.** Auth saves only the Playwright
  storage state.

Every action is logged to `logs/contentrewards-YYYYMMDD.log`.

## Session setup

1. Set `campaign_automation: true` in `config.yaml`.
2. Run `python3 -m clipsdaily.contentrewards auth`. A headed Chromium
   window opens at `https://contentrewards.com`. Log in by hand in
   that window, then press Enter in the terminal. The storage state is
   saved to `<runtime-home>/.auth/contentrewards_state.json` (mode
   0600). Nothing is submitted or joined during this step.
3. When the site expires the session (it will, eventually), re-run
   `auth`. There is no way to automate a re-login: only the account
   holder can do it. While the session is dead, join/submit/earnings
   refuse and the money loop degrades to "that leg paused" — the core
   posting loop is unaffected.

## How each command works

### join

Reads `join_requests.json` (written by `campaign_watcher.py`; each
entry has `campaign_id`, `url`, `title`, ...). For each request not
already recorded as `joined` in `join_results.json`: opens the campaign
URL, clicks Join, waits for the Joined badge. Appends
`{campaign_id, status: joined|failed, reason, at}` to
`join_results.json` (atomic write, one append per campaign). Already
joined campaigns are skipped without opening a browser. Idempotent:
re-running joins nothing twice.

### submit

Reads pending jobs through `auto_submit`'s own `--list-pending` logic
(imported, not reimplemented — same expiry behavior, same outbox
format). For each pending job, in order:

1. Window check (30 min from `posted_at`).
2. Queue-entry lookup (`queue.json` / `campaign_queue.json` by clip
   ID). No entry = fail: the gate cannot run without it.
3. Campaign lookup in `campaigns.json`. No campaign = fail.
4. `gate_clip` re-run (relative clip paths resolved against the
   runtime home). Fail = mark failed, never submit.
5. Dashboard pre-check: clip already there with an ID = mark
   submitted with that ID, do not re-file.
6. Open the campaign page, paste the clip URL into the submit form,
   complete it, wait for the on-page confirmation.
7. Open the submissions dashboard, find the row for the clip URL,
   require status Pending and a non-empty submission ID.
8. Mark submitted via `auto_submit --mark-submitted <job_id>
   --submission-id <id>` (the real CLI, run as a subprocess with
   `CLIPSDAILY_HOME` set). Any failure marks the job failed via
   `auto_submit --mark-failed <job_id> --reason <text>`.

### earnings-dump

Opens the submissions dashboard, scrapes every row into
`earnings_dump.json` in the exact format `earnings.py` consumes (see
`docs/AUTOMATION.md` and `earnings_dump_spec.md`):

```json
{"dumped_at": "2026-11-16T07:00:00",
 "submissions": [
   {"submission_id": "f9ecabc2-...",
    "clip_url": "https://youtube.com/shorts/...",
    "platform": "youtube",
    "campaign_id": "afeca1a0-...",
    "campaign_title": "$$8,000 Expedia x IShowSpeed Campaign",
    "status": "Pending",
    "views": 0,
    "payout_cents": 0,
    "submitted_at": "2026-11-15T14:26:00"}]}
```

Status is the dashboard text (Pending / Awaiting review / Approved /
Rejected). Then run `python3 -m clipsdaily.earnings --update` as usual.
If the dashboard is unreachable or its table cannot be found, the
command writes nothing and reports the failure plainly (exit code 1).

## Failure modes

| Failure | What the module does |
|---|---|
| `campaign_automation` false/absent | Refuses (exit 2), changes nothing |
| No session file | Refuses (exit 2), changes nothing |
| Session expired / login wall on a page | Page elements not found → that item fails with a reason; nothing claimed; re-run `auth` |
| Join button missing | Join failed, reason recorded |
| Joined badge not visible after click | Join failed, reason recorded — never claims the join |
| No pending jobs | Logs "no pending jobs", exit 0 |
| Job past 30-min window | Never submitted; marked `expired` by the outbox expiry (or failed `expired` if seen directly) |
| No queue entry / no campaign for a job | Mark failed ("cannot re-gate"), never submit |
| Gate fails at submit time | Mark failed with the gate reason, never submit |
| Clip URL field / submit button missing | Mark failed, nothing filed |
| No on-page submit confirmation | Mark failed, nothing claimed |
| Dashboard row missing / no submission ID after filing | Mark failed; the job stays failed for human review (do not re-file blindly — check the dashboard by hand first) |
| Dashboard unreachable (earnings) | Writes nothing, exit 1 |
| Dashboard table missing (login wall / site redesign) | Writes nothing, exit 1 |
| `mark-submitted` CLI fails after a verified dashboard row | Job left pending/failed with the reason; the next run's dashboard pre-check finds the existing row and marks it submitted instead of re-filing |
| Site redesign changes selectors | Everything fails closed (elements not found → failed, nothing claimed). Update `SELECTORS` in `contentrewards.py` + the fixture, re-run the tests, then the manual verification below |

## Selectors — UNVERIFIED against the real site

The `SELECTORS` table in `contentrewards.py` was written from the
Nov 15, 2026 browser sessions' descriptions, not from a live inspected
page. There is no test Content Rewards account, so the campaign-page
Join button, the submit-form fields, and the dashboard table layout
have **never been confirmed against the real site**. The unit tests run
against a local fixture that implements these selectors — a passing
test suite proves the logic (gates, expiry, idempotency, fail-closed
behavior), NOT that the selectors match contentrewards.com.

## Manual verification steps (do these before enabling live)

Do all of these with `campaign_automation: true` and a real session,
but **before pointing any timer at the module**, and with a throwaway
or already-joined campaign where possible:

1. **Auth.** Run `auth`, log in, confirm `.auth/contentrewards_state.json`
   exists, is mode 0600, and is non-empty. Confirm no password was
   asked for or stored anywhere.
2. **Join (already-joined campaign).** Put a campaign that is already
   joined into `join_requests.json` and run `join`. Expect: skipped,
   no browser navigation to the campaign page, `join_results.json`
   unchanged.
3. **Join (real).** With a genuinely unjoined campaign in
   `join_requests.json`, run `join`. Expect: the Joined badge appears
   on the site in a headed run, `join_results.json` gets `joined`, and
   the campaign's state on the site is Joined when checked by hand.
   If the Join button or badge selectors miss, the run records
   `failed` — update `SELECTORS`, update the fixture to match, re-run
   the tests.
4. **Submit (real, in-window).** With a freshly posted, gate-passing
   campaign clip in the outbox (posted < 30 min ago), run `submit`.
   Expect: the clip appears on the submissions dashboard as Pending
   with a submission ID, and the job is `submitted` with that ID.
   Then verify by hand on the dashboard that exactly one submission
   exists for the clip (no duplicate).
5. **Submit (already-submitted).** Re-run `submit` immediately.
   Expect: no pending jobs, zero new dashboard rows.
6. **Earnings.** Run `earnings-dump`, then `earnings.py --update`.
   Expect: `earnings_dump.json` rows match the dashboard row-for-row
   (IDs, URLs, statuses, views, payouts), and the earnings summary
   matches the dashboard totals.
7. **Flag-off.** Set `campaign_automation: false`, run all three
   commands. Expect: all refuse (exit 2), no files change, no browser
   opens.
8. **Session expiry.** (When it happens naturally.) Expect: commands
   refuse/fail closed with element-not-found reasons, nothing claimed;
   re-run `auth` to recover.

Only after steps 1–7 pass should the 15-minute submit timer and the
daily earnings timer be pointed at this module — and the first live
week should be watched in `logs/contentrewards-*.log` daily.

## Tests

`tests/test_contentrewards.py` (12 tests, local fixture server on
127.0.0.1, headless Chromium; no real credentials, no real site):

- join marks `joined` with the badge verified; missing badge = failed
- second join run skips already-joined without touching the site
- submit marks a gate-passing job `submitted` with the fixture
  submission ID; second run does not re-submit
- gate-failing clip is never submitted (job failed, zero fixture rows)
- expired job is never submitted (marked `expired`, zero fixture rows)
- earnings dump matches the fixture table row-for-row
- unreachable dashboard writes no `earnings_dump.json`
- `--dry-run` prints the plan, writes nothing to the outbox, makes
  zero HTTP requests
- flag-off refuses all three commands and changes nothing
- missing session refuses

Run: `PYTHONPATH=src python3 -m unittest tests.test_contentrewards -v`
(12 tests, ~60s on indra, Nov 16, 2026 — all passing).

What the tests **cannot** prove (see manual verification above): the
real Content Rewards login flow, the real campaign page structure, the
real submit-form selectors, and the real dashboard layout.
