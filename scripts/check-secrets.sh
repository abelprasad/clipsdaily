#!/bin/bash
# Secret scan for the clipsdaily repo. Fails (exit 1) if anything that
# looks like a real credential value is committed.
#
# Patterns (all are value-shaped, not bare names):
#   1. assignment-style secrets: api_key / password / token / cookie /
#      client_secret / access_token / private_key with a 16+ char value
#   2. token formats: Google ya29., GitHub ghp_/github_pat_, OpenAI sk-,
#      Slack xox[baprs]-, -----BEGIN ... PRIVATE KEY-----
#   3. cookie values: sessionid= / sid_tt= with a non-empty value
#
# Known-safe values are excluded: all-zero UUID placeholders,
# "your-...-here" placeholders, and the public Google OAuth client ID
# (a public identifier, not a secret — the client secret is what matters).
set -e
cd "$(dirname "$0")/.."
FAIL=0

scan() {
    # $1 = description, rest = grep args
    local desc="$1"; shift
    if grep -rInE --exclude-dir=__pycache__ --exclude-dir=.git "$@" \
        src docs scripts *.toml *.md *.json *.yml *.sh examples 2>/dev/null \
        | grep -v "00000000-0000-0000-0000-000000000000" \
        | grep -v "your-.*-here" \
        | grep -v "PLACEHOLDER" \
        | grep -v "157675679005-umk9q66t882rg7u5kcqur62hc5na6iq0.apps.googleusercontent.com"; then
        echo "SECRET SCAN FAIL: $desc" >&2
        FAIL=1
    fi
}

scan "assignment-style secret with a value" \
    '(api_key|apikey|password|passwd|secret|client_secret|access_token|refresh_token|private_key)[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9_\-\./]{16,}'

scan "token format (ya29./ghp_/github_pat_/sk-/xox-/private key)" \
    'ya29\.[A-Za-z0-9_\-]+|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9\-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'

scan "cookie value (sessionid/sid_tt with a value)" \
    '(sessionid|sid_tt)=[A-Za-z0-9_\-\.]{16,}'

if [ "$FAIL" = 1 ]; then
    echo "Secret scan FAILED — rotate the value first, then remove it from history." >&2
    exit 1
fi
echo "secret scan OK"
