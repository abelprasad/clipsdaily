"""Runtime-home resolution for the clipsdaily package.

The package code is installed (pip/pipx) or run from a checkout; the
RUNTIME state (config.yaml, queue/, .auth/, clips/, logs/, ...) lives in
the runtime home, which is:
  1. $CLIPSDAILY_HOME when set, else
  2. the current working directory.

Run the CLI from the runtime home (e.g. /home/abel/clipsdaily on indra),
or set CLIPSDAILY_HOME. Never point it at the repo checkout: the repo
is the dev copy and holds no live state.
"""

import os
from pathlib import Path


def runtime_home() -> Path:
    env = os.environ.get("CLIPSDAILY_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()
