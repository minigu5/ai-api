"""local-agent: hand a coding task to the cluster's local model and print a short report."""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from .config import load_config
from .harness import UnknownSession, run
from .preflight import PreflightError, check
from .setup import setup
from .workspace import NotARepo, changes, snapshot

EXIT_PREFLIGHT, EXIT_FAILED, EXIT_TIMEOUT, EXIT_INTERRUPTED = 2, 3, 4, 5
MAX_LINES = 30


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="local-agent",
        description="Have the school cluster's local model edit a git repository, then print a short report.")
    p.add_argument("prompt", help="what the worker should do, including how to check it is done")
    p.add_argument("--dir", default=".", help="git repository to work in (default: current folder)")
    p.add_argument("--model", help="cluster model id (default: LOCAL_AGENT_MODEL or Qwen3.6-35B-A3B-8bit)")
    p.add_argument("--harness", choices=["pi", "claude"], default="pi", help="worker program (default: pi)")
    p.add_argument("--continue", dest="session", metavar="SESSION", help="give more instructions in this session")
    p.add_argument("--timeout", type=int, metavar="SECONDS", help="stop the worker after this long (default: 1800)")
    return p


def _capped(text: str) -> str:
    """Keep each report section short so it does not flood the maintainer's context."""
    lines = text.splitlines()
    if not lines:
        return "(none)"
    if len(lines) <= MAX_LINES:
        return "\n".join(lines)
    return "\n".join(lines[:MAX_LINES] + [f"... {len(lines) - MAX_LINES} more lines, see log"])


def _report(status: str, session: str, seconds: int, summary: str, stat: str, new: list[str], log: Path) -> str:
    return "\n".join([
        f"status: {status}",
        f"session: {session}",
        f"time: {seconds}s",
        "summary:", _capped(summary),
        "changes:", _capped(stat),
        "new files:", _capped("\n".join(new)),
        f"log: {log}",
    ])


def main(argv: list[str] | None = None) -> int:
    if (argv if argv is not None else sys.argv[1:]) == ["--setup"]:
        try:
            setup(load_config(os.environ))
        except PreflightError as e:
            print(f"local-agent: {e}", file=sys.stderr)
            return EXIT_PREFLIGHT
        return 0
    args = _parser().parse_args(argv)
    cfg = load_config(os.environ, model=args.model, timeout=args.timeout)
    try:
        snap = snapshot(Path(args.dir))
        check(cfg)
        started = time.monotonic()
        result = run(args.harness, args.prompt, Path(args.dir).resolve(), cfg, args.session)
    except (NotARepo, PreflightError, UnknownSession) as e:
        print(f"local-agent: {e}", file=sys.stderr)
        return EXIT_PREFLIGHT
    seconds = round(time.monotonic() - started)
    try:
        stat, new = changes(snap)
    except subprocess.CalledProcessError as e:
        stat, new = f"(could not compute: {(e.stderr or '').strip() or e})", []
    if result.status == "ok":
        status, code = "ok", 0
    elif result.status == "interrupted":
        status, code = "interrupted", EXIT_INTERRUPTED
    elif result.status == "timeout":
        status, code = f"timeout ({cfg.timeout}s)", EXIT_TIMEOUT
    else:
        why = "model error" if result.exit_code == 0 else f"exit {result.exit_code}"
        status, code = f"failed ({why})", EXIT_FAILED
    print(_report(status, result.session, seconds, result.summary, stat, new, result.log_path))
    return code
