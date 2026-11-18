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
    status: Literal["ok", "failed", "timeout", "interrupted"]
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


def pi_error(jsonl_text: str) -> str:
    """The model's error text if its last message ended in an error; pi still exits 0 in that case."""
    error = ""
    for line in jsonl_text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") or {}
        if event.get("type") == "message_end" and message.get("role") == "assistant":
            error = (message.get("errorMessage") or "error") if message.get("stopReason") == "error" else ""
    return error.strip()


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


def _known_pi_session(cfg: Config, session: str, cwd: Path) -> bool:
    """pi resumes only a session whose header has this exact id and cwd; anything else starts a new one."""
    for path in (cfg.state_dir / "sessions").glob("*.jsonl"):
        try:
            with open(path) as f:
                header = json.loads(f.readline())
        except (OSError, ValueError):
            continue
        if header.get("id") == session and os.path.realpath(header.get("cwd", "")) == os.path.realpath(cwd):
            return True
    return False


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run(harness: Literal["pi", "claude"], prompt: str, cwd: Path, cfg: Config, session: str | None,
        *, which=shutil.which) -> RunResult:
    if which(harness) is None:
        raise PreflightError(f"{harness} is not installed or not on PATH")
    if harness == "pi":
        if session and not _known_pi_session(cfg, session, cwd):
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
        interrupted = False

        def stop(*_):
            nonlocal interrupted
            interrupted = True
            _kill_group(proc.pid)

        # If our caller kills us (e.g. a shell tool's time limit), take the worker down too and still report.
        previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
        try:
            code = proc.wait(timeout=cfg.timeout)
        except subprocess.TimeoutExpired:
            _kill_group(proc.pid)
            proc.wait()
            code = None
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    text = log_path.read_text(errors="replace")
    model_error = ""
    if harness == "pi":
        summary = pi_summary(text)
        model_error = pi_error(text)
        if model_error:
            summary = f"model error: {model_error}"
    else:
        summary, reported = claude_summary(text)
        session = reported or session or ""
    if interrupted:
        status = "interrupted"
    elif code is None:
        status = "timeout"
    else:
        status = "ok" if code == 0 and not model_error else "failed"
    return RunResult(status, code, summary, session, log_path)
