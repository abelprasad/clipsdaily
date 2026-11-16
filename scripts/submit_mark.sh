#!/bin/bash
# submit_mark.sh — record a browser submit result back on indra.
# Usage:
#   submit_mark.sh <job_id> submitted <submission_id>
#   submit_mark.sh <job_id> failed "<reason>"
# The submission_id must come from the Content Rewards dashboard
# showing the clip Pending. Never mark submitted without that ID.
set -u
JOB_ID="${1:?job_id required}"
RESULT="${2:?submitted|failed required}"
INDRA="/tmp/indra.sh"
if [ "$RESULT" = "submitted" ]; then
  SUB_ID="${3:?submission_id required}"
  "$INDRA" "sudo -n -u abel /home/abel/.local/bin/clipsdaily submit mark-submitted $JOB_ID --submission-id $SUB_ID"
elif [ "$RESULT" = "failed" ]; then
  REASON="${3:-}"
  "$INDRA" "sudo -n -u abel /home/abel/.local/bin/clipsdaily submit mark-failed $JOB_ID --reason \"$REASON\""
else
  echo "RESULT must be submitted|failed" >&2
  exit 1
fi
