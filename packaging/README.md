# ClipForge

Fully automatic Twitch/Kick clip pipeline: record, cut, post. Zero
human or agent intervention after a one-time setup.

**ClipForge is proprietary.** See `LICENSE` (no
redistribution, no resale, no sublicensing) and `BETA_TERMS.md`.
The repo is public to read (my call, Nov 17, 2026); public does
not mean open source. Do not copy `packaging/` into the public
skills repo.

## Install

```bash
./packaging/install.sh --license key.txt --accept-license
clipforge setup
```

Full steps, requirements, and the honest list of one-time human
setup steps (YouTube OAuth, TikTok developer review, Instagram
session, Content Rewards login): `packaging/INSTALL.md`.

## License keys

Every install needs a signed license key. The check is offline and
requires no server:

- **Format:** `CF1-<base64url(payload)>.<base64url(signature)>`,
  where payload is JSON
  `{"kid", "email", "exp": "YYYY-MM-DD", "tier"}`.
- **Signature:** Ed25519 over the raw payload bytes. The vendor
  private key is held by me only (never in this repo, the package,
  or the installer); the public key is baked into
  `src/clipsdaily/license.py`, so anyone can verify a key and only
  I can issue one.
- **What the installer checks:** format, signature against the
  baked-in public key, and expiry. A bad, tampered, or expired key
  refuses the install before any runtime state is created.
- **What the product checks:** the `clipforge` CLI refuses to run
  any service command (run, post, ig, watchdog, dashboard, setup,
  …) against a ClipForge runtime home without a valid installed key
  (`.auth/license.key`, 0600). `clipforge license status` and
  `clipforge status` still work so you can see why you are blocked.
- **Issuing a key (vendor):**
  `python3 packaging/tools/gen_license_key.py --email … --kid
  CF-BETA-0001 --exp 2027-06-30 --tier beta` — it loads the private
  key from `$CLIPFORGE_LICENSE_PRIVATE_KEY` or
  `/home/abel/.config/clipforge/license-private.key`.
- **Rotation:** replace the public key in `license.py`, reissue keys.
  Tests can override the public key with `--public-key` /
  `$CLIPFORGE_LICENSE_PUBLIC_KEY` (test-only).
- **What this does NOT do:** it stops a leaked copy from just
  running, and it ties each copy to a named tester with an expiry.
  It is not DRM — a determined reverse-engineer can bypass any
  client-side check. The real protection is the license terms plus
  the license-key gate. A future server check
  (revocation list / activation counting) would be added as a
  `verify_key_remote()` step in `license.py` that consults a vendor
  endpoint and caches the verdict; the local Ed25519 check stays as
  the offline fallback.

## What the GUI shows — and what it never shows

The dashboard (http://127.0.0.1:8787, localhost only) shows what a
customer needs to *operate* the product: watchlist, queue
(pending/posted/failed with per-platform status), post history with
links, per-platform health + last-post times, settings (posting
schedule, caps, platform toggles, kill switch, retention), and logs.

It deliberately does **not** show how the product works: no cutter
internals, no ranking weights, no chat-spike thresholds, no
transcription model details, no cut-window geometry, and no absolute
source paths. The tuning lives in `config.yaml` on the customer's
own box with minimal comments, and the design doc
(`docs/AUDIT_AND_DESIGN.md`) is internal-only — it is never copied
into a customer install and must not be published.

## Layout (repo)

- `packaging/` — installer, LICENSE, BETA_TERMS.md, this README,
  INSTALL.md, keygen tool. This is the product distribution.
- `src/clipsdaily/` — pipeline + `license.py`, `setup.py`,
  `dashboard.py`, `ig_poster.py`, `notifier.py`, `update.py`.
- `systemd/` — user units + timers (installed by install.sh).
- `config/config.yaml.example` — config template.
- `docs/` — internal design + audit docs (do not ship to customers).

## Public repo, proprietary license

As of Nov 17, 2026 (my decision) this repo is public to read at
`github.com/abelprasad/clipsdaily`, including the `packaging/` branch.
Public does NOT mean open source: the ClipForge Proprietary License
("licensed, not sold") still forbids redistribution, resale, and
sublicensing. The rules that still hold:

- Never copy `packaging/` into the public skills repo.
- The vendor private key is never committed, pasted in chat, or
  stored in the repo. If it is ever exposed, rotate the public key
  in `license.py` and reissue every key.
