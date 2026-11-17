#!/usr/bin/env python3
"""Issue a ClipForge license key (vendor tool — NOT shipped to customers).

Loads the vendor Ed25519 private key from:
  1. $CLIPFORGE_LICENSE_PRIVATE_KEY (path to the PEM file), or
  2. /home/abel/.config/clipforge/license-private.key (default)

and prints a CF1- key for one beta tester. The private key is NEVER
in this repo, the package, or the installer — without it this script
cannot sign anything.

Usage:
  python3 tools/gen_license_key.py --email beta@example.com \\
      --kid CF-BETA-0001 --exp 2027-06-30 --tier beta

The customer installs it with:
  ./install.sh --license key.txt
(or paste it when the installer asks).
"""
import argparse
import base64
import json
import sys
from pathlib import Path

DEFAULT_KEY_PATH = "/home/abel/.config/clipforge/license-private.key"


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", required=True)
    ap.add_argument("--kid", required=True,
                    help="key id, e.g. CF-BETA-0001")
    ap.add_argument("--exp", required=True,
                    help="expiry date YYYY-MM-DD")
    ap.add_argument("--tier", default="beta")
    ap.add_argument("--key", default=None,
                    help="private key PEM path (default: "
                         "$CLIPFORGE_LICENSE_PRIVATE_KEY or "
                         + DEFAULT_KEY_PATH + ")")
    args = ap.parse_args()

    import os
    key_path = args.key or os.environ.get("CLIPFORGE_LICENSE_PRIVATE_KEY") \
        or DEFAULT_KEY_PATH
    key_file = Path(key_path)
    if not key_file.exists():
        print("private key not found at %s — set "
              "CLIPFORGE_LICENSE_PRIVATE_KEY" % key_path, file=sys.stderr)
        return 1
    from cryptography.hazmat.primitives import serialization
    priv = serialization.load_pem_private_key(
        key_file.read_bytes(), password=None)
    payload = {"kid": args.kid, "email": args.email,
               "exp": args.exp, "tier": args.tier}
    payload_bytes = json.dumps(payload, separators=(",", ":"),
                               sort_keys=True).encode()
    sig = priv.sign(payload_bytes)
    key = "CF1-%s.%s" % (_b64e(payload_bytes), _b64e(sig))
    print(key)
    print("kid=%s email=%s exp=%s tier=%s"
          % (args.kid, args.email, args.exp, args.tier), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
