"""ClipForge notifier: deliver watchdog health alerts to the customer.

Channels (config.yaml `notify:`, default `none` = log-only):
  none     — alerts stay in logs/health-alerts.log + health.json.
  email    — SMTP. Settings in config.yaml under notify.email
             (host, port, from, to, user); the password comes from the
             CLIPFORGE_SMTP_PASS environment variable ONLY — never from
             config, chat, or a log.
  discord  — webhook. URL from config.yaml notify.discord.webhook_url,
             or the CLIPFORGE_DISCORD_WEBHOOK environment variable.

notify_alert() never raises: a notification failure is logged and the
alert itself is already in health-alerts.log, so nothing is lost.
"""
import json
import os
import smtplib
import time
import urllib.request
from email.message import EmailMessage
from pathlib import Path

import yaml

from .branding import BRAND_NAME
from .paths import runtime_home

HERE = runtime_home()


def _load_notify_config():
    try:
        cfg = yaml.safe_load((HERE / "config.yaml").read_text()) or {}
    except Exception:
        return {}
    notify = cfg.get("notify") or {}
    return notify if isinstance(notify, dict) else {}


def _send_email(settings, subject, body):
    host = settings.get("host", "")
    port = int(settings.get("port", 587))
    sender = settings.get("from", "")
    to = settings.get("to", "")
    user = settings.get("user", "")
    password = os.environ.get("CLIPFORGE_SMTP_PASS", "")
    if not host or not sender or not to:
        raise ValueError("email notify needs host/from/to in config.yaml")
    if not password:
        raise ValueError("email notify needs CLIPFORGE_SMTP_PASS set")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(body)
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user or sender, password)
        s.send_message(msg)


def _send_discord(webhook_url, text):
    if not webhook_url:
        raise ValueError("discord notify needs a webhook URL")
    payload = json.dumps({"content": text}).encode()
    req = urllib.request.Request(
        webhook_url, data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def notify_alert(platform, detail):
    """Send one health alert. Returns True if a channel delivered it,
    False if notify is off or every channel failed (logged by caller)."""
    notify = _load_notify_config()
    channel = (notify.get("channel") or "none").lower()
    if channel == "none":
        return False
    subject = "[%s] %s failure: %s" % (BRAND_NAME, platform, detail[:80])
    body = ("%s health alert\n\nPlatform: %s\nDetail: %s\nTime: %s\n\n"
            "See health.json and logs/health-alerts.log in the runtime home."
            % (BRAND_NAME, platform, detail,
               time.strftime("%Y-%m-%d %H:%M:%S")))
    try:
        if channel == "email":
            _send_email(notify.get("email") or {}, subject, body)
        elif channel == "discord":
            url = (notify.get("discord") or {}).get("webhook_url") or \
                os.environ.get("CLIPFORGE_DISCORD_WEBHOOK", "")
            _send_discord(url, subject + "\n" + body)
        else:
            raise ValueError("unknown notify channel %r" % channel)
        return True
    except Exception as e:
        print("[notifier] %s delivery failed: %s" % (channel, e),
              flush=True)
        return False
