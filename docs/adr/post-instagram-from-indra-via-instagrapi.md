# Post Instagram from indra via instagrapi

## Status

Accepted. 2026-11-17.

## Context

Instagram posting ran from the operator VM via `instagram-cli`, and
every run needed a one-time runtime approval. Overnight runs timed out
while Abel slept (02:05, 02:37, 04:36, 07:05 on Nov 17), so no clips
posted for hours. A durable schedule-scoped grant could not be
pre-approved — the connector method refuses pre-approval. The
operator-VM route also depends on a browser session the operator VM
cannot reproduce on indra (glibc 2.39 + privsep socket).

Separately, instagrapi password login was believed broken: version
3.1.0 failed at `password_publickeys` (the `qe/sync/` endpoint 404s
without key headers). Research on Nov 17 found instagrapi 3.2.15
(released Nov 15, 2026, Python >= 3.11) and that the bug was fixed
upstream in 3.2.3 (key now fetched from `launcher/sync/`).

## Decision

Post Instagram from indra: a venv (`.venv-ig`, Python 3.13.18 via uv)
with `instagrapi==3.2.15` pinned, a oneshot systemd service
(`clipsdaily-ig-post.service`, `ExecStart` = venv python +
`ig_post_staged.py`) and a timer (`OnCalendar=*:05,35`,
`Persistent=true`). `ig_post_staged.py` replicates the VM script
exactly (slot window, caption verbatim, ffmpeg cover at 1s, clip
upload, `.posted` marker, `staged` → `posted` flip); a missing or
expired session logs and exits 0 (timer-safe) and honors `STOP`.
Authentication is session-cookie import only: `auth_ig_session.py`
takes a browser `cookies.txt`, imports the sessionid via
`login_by_sessionid`, verifies the account id, writes
`.auth/instagram_session.json` (0600), never prints the sessionid and
never copies the cookies file. Password login
(`CLIPSDAILY_IG_PASS` env, never on disk) is the fallback; it was never
tested end to end. The VM cron stays on until the indra route posts
live; the `.posted` marker prevents double-posting while both run.

## Consequences

- The approval-timeout stall is gone by design: no per-run approval
  exists on indra.
- The encryption-key fix was verified live with no credentials
  (`Client().password_publickeys()` returns a key id + public key).
  The actual login was never tested before shutdown, so the end-to-end
  post is still unproven — a restart must test it first.
- instagrapi is an unofficial client: it violates Instagram's Terms,
  and fresh logins can still be blocked (CAA/Bloks 404s, HTTP 429,
  datacentre IPs). The official Meta Content Publishing API remains the
  documented alternative (see `docs/AUTH.md`).
- The same day this shipped, Instagram flagged the account for
  unoriginal content — a posting-route fix does not fix a
  content-originality problem (see ADR 018).
