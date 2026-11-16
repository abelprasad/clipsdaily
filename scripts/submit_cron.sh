#!/bin/bash
# submit_cron.sh — parent-VM helper for the clipsdaily auto-submit loop.
# Run by the parent's cron every 15 minutes. Steps:
#   1. Run auto_submit.py --scan on indra (writes submit jobs for newly
#      posted campaign clips, re-gating each one; expires stale jobs).
#   2. Pull pending jobs as JSON and print them for the cron agent.
# The cron agent then submits each pending job in the cloud browser on
# Content Rewards, verifies the dashboard shows Pending WITH a
# submission ID, and marks the result with submit_mark.sh.
# This script itself never submits anything and never touches a browser.
set -u
INDRA="/tmp/indra.sh"
if [ ! -x "$INDRA" ]; then
  cp ~/workspace/ssh-tail-proxy.py /tmp/ssh-tail-proxy.py 2>/dev/null
  chmod 600 /tmp/ssh-tail-proxy.py 2>/dev/null
  cat > "$INDRA" <<'EOF'
#!/bin/bash
exec ssh -o UserKnownHostsFile=/home/hatch/.ssh/known_hosts -i /home/hatch/.ssh/id_ed25519 -o ProxyCommand="python3 /tmp/ssh-tail-proxy.py %h %p" friday@100.78.151.90 "$@"
EOF
  chmod 700 "$INDRA"
fi
echo "=== auto_submit --scan (indra) ==="
"$INDRA" 'sudo -n -u abel python3 /home/abel/clipsdaily/auto_submit.py --scan'
echo "=== pending submit jobs ==="
"$INDRA" 'sudo -n -u abel python3 /home/abel/clipsdaily/auto_submit.py --list-pending'
