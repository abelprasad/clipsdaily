# Documentation

- [Quickstart](quickstart.md) — zero to a running pipeline
- [Installation](installation.md) — one-command install, from source, system deps
- [CLI reference](cli-reference.md) — generated from the real CLI (`make docs` regenerates it)
- [Configuration](configuration.md) — runtime home, `config.yaml`, `campaigns.json`, env vars
- [Operations](OPERATIONS.md) — processes, hourly cadence, limits, kill switch, cleanup, crons, logs, VOD batch
- [Campaigns](CAMPAIGNS.md) — campaign discovery, join rules, cutting, the gate, submitting
- [Auth](AUTH.md) — YouTube OAuth, TikTok cookies, Instagram (operator CLI)
- [TikTok](TIKTOK.md) — the auto-posting block, what works, what doesn't
- [Captions](CAPTIONS.md) — one-line captions, hook rules, hashtag policy
- [Automation](AUTOMATION.md) — the full-automation design (watcher, gate, outbox, earnings)
- [Submit cron body](SUBMIT_CRON_BODY.md) — what the 15-min auto-submit cron does
- [Earnings dump spec](earnings_dump_spec.md) — the browser dump `earnings.py` consumes
- [YouTube VOD notes](youtube-vod-notes.md) — the paused VOD phase design
- [Path assumptions](PATHS.md) — hardcoded paths, what a new operator must change
- [FAQ](faq.md)
- [Architecture decisions](adr/) — 15 ADRs, Nygard template, immutable
