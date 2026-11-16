"""clipsdaily command-line interface.

Thin entry layer over the pipeline modules in this package. Each
subcommand lazily imports the module it wraps, so `clipsdaily --help`
stays fast and never pulls in torch/whisper/playwright.

Runtime state lives in the runtime home: $CLIPSDAILY_HOME when set,
else the current working directory (see clipsdaily.paths). Run the CLI
from the runtime home (e.g. /home/abel/clipsdaily on indra), or pass
--home. Never point it at the repo checkout: the repo is the dev copy
and holds no live state.

Subcommands:
  run       live runner (record + chat spikes + cut + post)
  post      post clips (now / one / hourly)
  queue     queue status / maintainer / seed
  campaign  campaign watch / cut
  submit    auto-submit outbox (scan / list-pending / mark-*)
  earnings  earnings summary / update
  auth      auth setup (youtube / tiktok / instagram) and auth check

Every module in this package also runs directly:
  python -m clipsdaily.runner
  python -m clipsdaily.cutter recordings/x.mp4 45 channel
"""

import argparse
import os
import runpy
import sys

from . import __version__


def _set_argv(prog, *args):
    sys.argv = [prog, *args]


def _cmd_run(args):
    from . import runner

    runner.main()


def _cmd_post_now(args):
    from . import post_now

    post_now.main()


def _cmd_post_one(args):
    from . import post_one

    argv = ["post_one.py", args.clip_id]
    if args.slot:
        argv.append(args.slot)
    _set_argv(*argv)
    post_one.main()


def _cmd_post_hourly(args):
    from . import hourly_poster

    hourly_poster.main()


def _cmd_queue_status(args):
    from . import queue_seed

    try:
        entries = queue_seed.load_queue()
    except FileNotFoundError:
        print("queue empty: no queue.json in the runtime home")
        return 0
    by_status = {}
    for e in entries:
        by_status[e.get("status", "?")] = by_status.get(e.get("status", "?"), 0) + 1
    print(f"queue: {len(entries)} entries")
    for st in sorted(by_status):
        print(f"  {st}: {by_status[st]}")
    pending = [e for e in entries if e.get("status") in ("pending", "partial")]
    if pending:
        nxt = pending[0]
        print(f"next: {nxt['id']} ({nxt.get('streamer', '?')})")
    return 0


def _cmd_queue_maintain(args):
    from . import queue_seed

    _set_argv("queue_seed.py", "--maintain")
    queue_seed.main()


def _cmd_queue_seed(args):
    from . import queue_seed

    argv = ["queue_seed.py", "--seed"]
    if args.target:
        argv.append(str(args.target))
    _set_argv(*argv)
    queue_seed.main()


def _cmd_campaign_watch(args):
    # campaign_watcher has no main(): its CLI lives under __main__.
    argv = ["campaign_watcher.py"]
    if args.check:
        argv.append("--check")
    if args.dry_run:
        argv.append("--dry-run")
    if args.discover_only:
        argv.append("--discover-only")
    _set_argv(*argv)
    runpy.run_module("clipsdaily.campaign_watcher", run_name="__main__")


def _cmd_campaign_cut(args):
    from . import campaign_cut

    argv = ["campaign_cut.py", "--campaign", args.campaign,
            "--max-clips", str(args.max_clips)]
    if args.dry_run:
        argv.append("--dry-run")
    _set_argv(*argv)
    campaign_cut.main()


def _cmd_submit(args):
    from . import auto_submit

    argv = ["auto_submit.py"]
    if args.action == "scan":
        argv.append("--scan")
    elif args.action == "list-pending":
        argv.append("--list-pending")
    elif args.action == "write-job":
        argv += ["--write-job", args.entry_json, args.platform]
    elif args.action == "mark-submitted":
        argv += ["--mark-submitted", args.job_id,
                 "--submission-id", args.submission_id]
    elif args.action == "mark-failed":
        argv += ["--mark-failed", args.job_id]
        if args.reason:
            argv += ["--reason", args.reason]
    _set_argv(*argv)
    auto_submit.main()


def _cmd_earnings(args):
    from . import earnings

    argv = ["earnings.py"]
    if args.update:
        argv.append("--update")
    if args.summary:
        argv.append("--summary")
    _set_argv(*argv)
    earnings.main()


def _cmd_auth(args):
    if args.target == "youtube":
        from . import auth_youtube

        auth_youtube.main()
    elif args.target == "tiktok":
        from . import auth_tiktok

        auth_tiktok.main()
    elif args.target == "instagram":
        from . import auth_instagram

        auth_instagram.main()
    elif args.target == "check":
        from . import poster

        poster.check_all()


def build_parser():
    p = argparse.ArgumentParser(
        prog="clipsdaily",
        description="Fully automatic stream clip pipeline: record, cut, post.",
    )
    p.add_argument("--version", action="version",
                   version=f"%(prog)s {__version__}")
    p.add_argument("--home", metavar="DIR",
                   help="runtime home (default: $CLIPSDAILY_HOME or cwd)")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    p_run = sub.add_parser("run", help="live runner (record + spikes + cut + post)")
    p_run.set_defaults(func=_cmd_run)

    p_post = sub.add_parser("post", help="post clips")
    post_sub = p_post.add_subparsers(dest="post_command", metavar="POST")
    p_now = post_sub.add_parser("now", help="post the next pending queue clip now")
    p_now.set_defaults(func=_cmd_post_now)
    p_one = post_sub.add_parser("one", help="post one queue clip by id")
    p_one.add_argument("clip_id", help="queue entry id, e.g. jynxzi-2928767125-12505s")
    p_one.add_argument("slot", nargs="?", help="slot label (default: current hour)")
    p_one.set_defaults(func=_cmd_post_one)
    p_hourly = post_sub.add_parser("hourly", help="hourly poster loop (slots :00/:30)")
    p_hourly.set_defaults(func=_cmd_post_hourly)

    p_queue = sub.add_parser("queue", help="clip queue")
    queue_sub = p_queue.add_subparsers(dest="queue_command", metavar="QUEUE")
    q_status = queue_sub.add_parser("status", help="show queue counts + next clip")
    q_status.set_defaults(func=_cmd_queue_status)
    q_maintain = queue_sub.add_parser("maintain", help="maintainer loop (seed >=24)")
    q_maintain.set_defaults(func=_cmd_queue_maintain)
    q_seed = queue_sub.add_parser("seed", help="cut clips until N pending, then exit")
    q_seed.add_argument("target", nargs="?", type=int, help="pending target (default 24)")
    q_seed.set_defaults(func=_cmd_queue_seed)

    p_camp = sub.add_parser("campaign", help="campaign automation")
    camp_sub = p_camp.add_subparsers(dest="campaign_command", metavar="CAMPAIGN")
    c_watch = camp_sub.add_parser("watch", help="watch Content Rewards for campaigns")
    c_watch.add_argument("--check", action="store_true", help="full run (default)")
    c_watch.add_argument("--dry-run", action="store_true")
    c_watch.add_argument("--discover-only", action="store_true")
    c_watch.set_defaults(func=_cmd_campaign_watch)
    c_cut = camp_sub.add_parser("cut", help="cut clips for a joined campaign")
    c_cut.add_argument("--campaign", required=True, help="campaign id")
    c_cut.add_argument("--max-clips", type=int, default=2)
    c_cut.add_argument("--dry-run", action="store_true")
    c_cut.set_defaults(func=_cmd_campaign_cut)

    p_submit = sub.add_parser("submit", help="auto-submit outbox")
    submit_sub = p_submit.add_subparsers(dest="action", metavar="ACTION")
    s_scan = submit_sub.add_parser("scan", help="scan queue for submittable clips")
    s_scan.set_defaults(func=_cmd_submit)
    s_list = submit_sub.add_parser("list-pending", help="list pending submit jobs (JSON)")
    s_list.set_defaults(func=_cmd_submit)
    s_write = submit_sub.add_parser("write-job", help="write one submit job")
    s_write.add_argument("entry_json")
    s_write.add_argument("platform")
    s_write.set_defaults(func=_cmd_submit)
    s_sub = submit_sub.add_parser("mark-submitted", help="mark a job submitted")
    s_sub.add_argument("job_id")
    s_sub.add_argument("--submission-id", required=True,
                       help="dashboard submission ID (Pending proof)")
    s_sub.set_defaults(func=_cmd_submit)
    s_fail = submit_sub.add_parser("mark-failed", help="mark a job failed")
    s_fail.add_argument("job_id")
    s_fail.add_argument("--reason", default="")
    s_fail.set_defaults(func=_cmd_submit)

    p_earn = sub.add_parser("earnings", help="earnings summary / update")
    p_earn.add_argument("--update", action="store_true")
    p_earn.add_argument("--summary", action="store_true")
    p_earn.set_defaults(func=_cmd_earnings)

    p_auth = sub.add_parser("auth", help="auth setup and checks")
    p_auth.add_argument("target", choices=["youtube", "tiktok", "instagram", "check"],
                        help="youtube/tiktok/instagram run the setup flow; "
                        "check is the read-only poster auth check")
    p_auth.set_defaults(func=_cmd_auth)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.home:
        os.environ["CLIPSDAILY_HOME"] = args.home
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    return func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
