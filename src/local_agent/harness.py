"""Run a worker harness (pi or claude -p) against the cluster model and collect its final answer."""
import json
import os
import shutil
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import Config
from .preflight import PreflightError, read_token


@dataclass
class RunResult:
    status: Literal["ok", "failed", "timeout"]
    exit_code: int | None
    summary: str
    session: str
    log_path: Path


class UnknownSession(Exception):
    pass


def pi_summary(jsonl_text: str) -> str:
    last = ""
    for line in jsonl_text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") or {}
        if event.get("type") == "message_end" and message.get("role") == "assistant":
            texts = [c.get("text", "") for c in message.get("content", []) if c.get("type") == "text"]
            if any(t.strip() for t in texts):
                last = "".join(texts)
    return last.strip()


def claude_summary(json_text: str) -> tuple[str, str]:
    try:
        data = json.loads(json_text)
    except ValueError:
        return "", ""
    return (data.get("result") or "").strip(), data.get("session_id") or ""


def _pi_command(prompt: str, cfg: Config, session: str) -> tuple[list[str], dict[str, str]]:
    argv = ["pi", "-p", "--mode", "json", "--model", f"cluster/{cfg.model}",
            "--session-dir", str(cfg.state_dir / "sessions"), "--session-id", session, prompt]
    env = {"PI_CODING_AGENT_DIR": str(cfg.pi_dir), "PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1",
           "NODE_EXTRA_CA_CERTS": str(cfg.ca_path)}
    return argv, env


def _claude_command(prompt: str, cfg: Config, session: str | None) -> tuple[list[str], dict[str, str]]:
    argv = ["claude", "-p", prompt, "--output-format", "json", "--dangerously-skip-permissions"]
    if session:
        argv += ["--resume", session]
    env = {"ANTHROPIC_BASE_URL": cfg.gateway, "ANTHROPIC_AUTH_TOKEN": read_token(cfg),
           "ANTHROPIC_MODEL": cfg.model, "ANTHROPIC_SMALL_FAST_MODEL": cfg.model,
           "NODE_EXTRA_CA_CERTS": str(cfg.ca_path), "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    return argv, env


def _known_pi_session(cfg: Config, session: str) -> bool:
    sessions = cfg.state_dir / "sessions"
    return sessions.is_dir() and any(session in p.name for p in sessions.rglob("*") if p.is_file())


def run(harness: Literal["pi", "claude"], prompt: str, cwd: Path, cfg: Config, session: str | None,
        *, which=shutil.which) -> RunResult:
    if which(harness) is None:
        raise PreflightError(f"{harness} is not installed or not on PATH")
    if harness == "pi":
        if session and not _known_pi_session(cfg, session):
            raise UnknownSession(f"no pi session {session} under {cfg.state_dir / 'sessions'}")
        session = session or str(uuid.uuid4())
        argv, extra = _pi_command(prompt, cfg, session)
    else:
        argv, extra = _claude_command(prompt, cfg, session)
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"} | extra

    logs = cfg.state_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"{time.strftime('%Y%m%d-%H%M%S')}-{harness}.log"
    with open(log_path, "w") as out, open(log_path.with_name(log_path.name + ".err"), "w") as err:
        # Own process group, so a timeout also stops the shell commands the worker started.
        proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                env=env, start_new_session=True)
        try:
            code = proc.wait(timeout=cfg.timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            code = None

    text = log_path.read_text(errors="replace")
    if harness == "pi":
        summary = pi_summary(text)
    else:
        summary, reported = claude_summary(text)
        session = reported or session or ""
    status = "timeout" if code is None else ("ok" if code == 0 else "failed")
    return RunResult(status, code, summary, session, log_path)
