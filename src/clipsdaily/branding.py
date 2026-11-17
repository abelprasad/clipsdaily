"""ClipForge brand — single source of truth for the product name.

The product name is ClipForge (locked Nov 16, 2026). Every user-facing
surface — installer, setup wizard, dashboard, systemd units, docs —
imports these constants instead of hardcoding the name, so a future
rename is a one-line change here (plus the Python package rename, which
is a separate step and has NOT been done: the package is still
`clipsdaily` internally, and the live system is still ClipsDaily).

Do NOT rename the live /home/abel/clipsdaily/ pipeline from here.
"""

BRAND_NAME = "ClipForge"
BRAND_SLUG = "clipforge"
BRAND_CLI = "clipforge"
BRAND_TAGLINE = "Fully automatic stream clip pipeline: record, cut, post."
BRAND_HOMEPAGE = "https://github.com/abelprasad/clipforge"
