"""local-agent: hand a coding task to the cluster's local model and print a short report."""
import argparse
import os
import sys
import time
from pathlib import Path

from .config import load_config
from .harness import UnknownSession, run
from .preflight import PreflightError, check
from .workspace import NotARepo, changes, snapshot

EXIT_PREFLIGHT, EXIT_FAILED, EXIT_TIMEOUT = 2, 3, 4


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


def _report(status: str, session: str, seconds: int, summary: str, stat: str, new: list[str], log: Path) -> str:
    return "\n".join([
        f"status: {status}",
        f"session: {session}",
        f"time: {seconds}s",
        "summary:", summary or "(none)",
        "changes:", stat or "(none)",
        "new files:", "\n".join(new) or "(none)",
        f"log: {log}",
    ])


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cfg = load_config(os.environ, model=args.model, timeout=args.timeout)
    try:
        snap = snapshot(Path(args.dir))
        check(cfg)
        started = time.monotonic()
        result = run(args.harness, args.prompt, snap.root, cfg, args.session)
    except (NotARepo, PreflightError, UnknownSession) as e:
        print(f"local-agent: {e}", file=sys.stderr)
        return EXIT_PREFLIGHT
    seconds = round(time.monotonic() - started)
    stat, new = changes(snap)
    if result.status == "ok":
        status, code = "ok", 0
    elif result.status == "timeout":
        status, code = f"timeout ({cfg.timeout}s)", EXIT_TIMEOUT
    else:
        status, code = f"failed (exit {result.exit_code})", EXIT_FAILED
    print(_report(status, result.session, seconds, result.summary, stat, new, result.log_path))
    return code
