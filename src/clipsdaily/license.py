"""ClipForge license-key verification — offline, Ed25519.

Key format:
    CF1-<base64url(payload)>.<base64url(signature)>
where payload is UTF-8 JSON:
    {"kid": "CF-BETA-0001", "email": "beta@example.com",
     "exp": "2027-06-30", "tier": "beta"}

The signature is Ed25519 over the raw payload bytes, made with the
vendor private key. That key is held by Abel only — it is NEVER in
this repo, the package, or the installer. The public key is baked
into this module: anyone can verify a key, only Abel can issue one.

Verification is fully offline (no server, no network): a leaked copy
of the package does not run without a signed key. Expiry is enforced
locally (a key past its `exp` date refuses). Revocation / activation
counting would need a server check — deliberately NOT built; see
README section "License keys" for how one would be added later.

This module never signs. Key issuance lives in tools/gen_license_key.py,
which loads the private key from the vendor's machine.
"""
import base64
import binascii
import json
from datetime import date

# Vendor public key (Ed25519, PEM). Generated Nov 16, 2026; the matching
# private key lives at /home/abel/.config/clipforge/license-private.key
# on indra (0600, abel-owned) and must be moved to the Secure Vault.
# Rotate by replacing this PEM and reissuing keys.
PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAdYG5SGC4ScEnB7lxT6R3Ip/6GBvnv/uCaB5MT/79Z+k=
-----END PUBLIC KEY-----
"""

KEY_FILE_NAME = "license.key"


class LicenseError(Exception):
    pass


def _b64d(s):
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def parse_key(key_str):
    """Split + decode a key. Returns (payload_bytes, payload, signature).
    Raises LicenseError on any format problem."""
    key_str = (key_str or "").strip()
    if not key_str.startswith("CF1-"):
        raise LicenseError("key must start with CF1-")
    body = key_str[4:]
    if body.count(".") != 1:
        raise LicenseError("key must have exactly one '.' separator")
    payload_b64, sig_b64 = body.split(".")
    try:
        payload_bytes = _b64d(payload_b64)
        signature = _b64d(sig_b64)
    except (binascii.Error, ValueError):
        raise LicenseError("key is not valid base64url")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise LicenseError("key payload is not valid JSON")
    if not isinstance(payload, dict):
        raise LicenseError("key payload must be a JSON object")
    for field in ("kid", "email", "exp", "tier"):
        if field not in payload:
            raise LicenseError("key payload is missing %r" % field)
    if len(signature) != 64:
        raise LicenseError("signature must be 64 bytes (Ed25519)")
    return payload_bytes, payload, signature


def verify_key(key_str, public_key_pem=None):
    """Verify a license key. Returns a dict:
    {"valid": bool, "kid": str|None, "email": str|None,
     "expires": str|None, "tier": str|None, "error": str|None}.
    Never raises."""
    try:
        payload_bytes, payload, signature = parse_key(key_str)
    except LicenseError as e:
        return {"valid": False, "kid": None, "email": None,
                "expires": None, "tier": None, "error": str(e)}
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        pub = serialization.load_pem_public_key(
            (public_key_pem or PUBLIC_KEY_PEM).encode())
        pub.verify(signature, payload_bytes)
    except ImportError:
        return {"valid": False, "kid": payload.get("kid"),
                "email": payload.get("email"),
                "expires": payload.get("exp"),
                "tier": payload.get("tier"),
                "error": "cryptography library not installed — "
                         "cannot verify the key"}
    except InvalidSignature:
        return {"valid": False, "kid": payload.get("kid"),
                "email": payload.get("email"),
                "expires": payload.get("exp"),
                "tier": payload.get("tier"),
                "error": "signature invalid — key was not issued by "
                         "the vendor (or was tampered with)"}
    except Exception as e:
        return {"valid": False, "kid": payload.get("kid"),
                "email": payload.get("email"),
                "expires": payload.get("exp"),
                "tier": payload.get("tier"),
                "error": "verification failed: %s" % e}
    try:
        exp = date.fromisoformat(str(payload["exp"]))
    except ValueError:
        return {"valid": False, "kid": payload.get("kid"),
                "email": payload.get("email"),
                "expires": str(payload.get("exp")),
                "tier": payload.get("tier"),
                "error": "exp is not a YYYY-MM-DD date"}
    if exp < date.today():
        return {"valid": False, "kid": payload.get("kid"),
                "email": payload.get("email"),
                "expires": str(payload.get("exp")),
                "tier": payload.get("tier"),
                "error": "key expired on %s" % payload["exp"]}
    return {"valid": True, "kid": payload.get("kid"),
            "email": payload.get("email"),
            "expires": str(payload.get("exp")),
            "tier": payload.get("tier"), "error": None}


def load_installed_key(home):
    """Verify the key installed in <home>/.auth/license.key.
    Returns the verify_key dict, or {"valid": False, ...} when no key
    is installed. Honors $CLIPFORGE_LICENSE_PUBLIC_KEY (path to a PEM)
    as a public-key override — test-only / key rotation; the baked-in
    vendor key is the default."""
    import os
    from pathlib import Path
    key_file = Path(home) / ".auth" / KEY_FILE_NAME
    if not key_file.exists():
        return {"valid": False, "kid": None, "email": None,
                "expires": None, "tier": None,
                "error": "no license key installed (.auth/license.key "
                         "missing)"}
    try:
        key_str = key_file.read_text().strip()
    except Exception as e:
        return {"valid": False, "kid": None, "email": None,
                "expires": None, "tier": None,
                "error": "cannot read license key: %s" % e}
    pub = None
    override = os.environ.get("CLIPFORGE_LICENSE_PUBLIC_KEY")
    if override:
        try:
            pub = Path(override).read_text()
        except Exception as e:
            return {"valid": False, "kid": None, "email": None,
                    "expires": None, "tier": None,
                    "error": "cannot read override public key %s: %s"
                             % (override, e)}
    return verify_key(key_str, public_key_pem=pub)


def key_status(home):
    """(ok, detail) one-liner for `clipforge status` / `license status`."""
    res = load_installed_key(home)
    if res["valid"]:
        return True, ("licensed to %s (key %s, tier %s, expires %s)"
                      % (res["email"], res["kid"], res["tier"],
                         res["expires"]))
    return False, ("license: %s" % res["error"])
