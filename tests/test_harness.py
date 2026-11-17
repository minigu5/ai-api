import json
import os
import stat
from pathlib import Path

import pytest

from local_agent.config import load_config
from local_agent.harness import UnknownSession, claude_summary, pi_summary, run
from local_agent.preflight import PreflightError

FIX = Path(__file__).parent / "fixtures"


def fake(bin_dir: Path, name: str, body: str) -> Path:
    """A stand-in worker that records argv and env, then runs `body`."""
    bin_dir.mkdir(exist_ok=True)
    p = bin_dir / name
    p.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys, time, subprocess\n"
        f"open({str(bin_dir / (name + '.call'))!r}, 'w').write(json.dumps({{'argv': sys.argv[1:], 'env': dict(os.environ), 'cwd': os.getcwd(), 'pid': os.getpid()}}))\n"
        + body
    )
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def call(bin_dir, name):
    return json.loads((bin_dir / (name + ".call")).read_text())


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "token").write_text("secret-token\n")
    bin_dir = tmp_path / "bin"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "real-key")
    cfg = load_config({"LOCAL_AGENT_HOME": str(home), "XDG_STATE_HOME": str(tmp_path / "state")})
    work = tmp_path / "work"
    work.mkdir()
    return cfg, bin_dir, work


def test_pi_summary_fixture():
    assert pi_summary((FIX / "pi-run.jsonl").read_text()).startswith("All 10 tests pass.")


def test_claude_summary_fixture():
    summary, session = claude_summary((FIX / "claude-run.json").read_text())
    assert summary.startswith("모든 16개 테스트 통과")
    assert session


def test_pi_argv_and_env(env):
    cfg, bin_dir, work = env
    fake(bin_dir, "pi", f"sys.stdout.write(open({str(FIX / 'pi-run.jsonl')!r}).read())\n")
    r = run("pi", "do it", work, cfg, None)
    c = call(bin_dir, "pi")
    assert r.status == "ok" and r.exit_code == 0
    assert r.summary.startswith("All 10 tests pass.")
    assert c["argv"][c["argv"].index("--session-id") + 1] == r.session
    assert f"cluster/{cfg.model}" in c["argv"]
    assert c["argv"][-1] == "do it"
    assert c["env"]["PI_CODING_AGENT_DIR"] == str(cfg.pi_dir)
    assert c["env"]["NODE_EXTRA_CA_CERTS"] == str(cfg.ca_path)
    assert "secret-token" not in " ".join(c["argv"])
    assert r.log_path.exists()


def test_prompt_passed_verbatim(env):
    cfg, bin_dir, work = env
    fake(bin_dir, "pi", "")
    prompt = 'say "hi"\nline2 $(rm -rf x) \'q\''
    run("pi", prompt, work, cfg, None)
    assert call(bin_dir, "pi")["argv"][-1] == prompt


def test_pi_continue_unknown_session(env):
    cfg, bin_dir, work = env
    fake(bin_dir, "pi", "")
    with pytest.raises(UnknownSession):
        run("pi", "again", work, cfg, "no-such-id")
    assert not (bin_dir / "pi.call").exists()


def write_session(cfg, session_id, cwd):
    sessions = cfg.state_dir / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    header = {"type": "session", "version": 3, "id": session_id, "timestamp": "2026-11-17T04:49:15.193Z",
              "cwd": os.path.realpath(cwd)}
    (sessions / f"2026-11-17T04-49-15-193Z_{session_id}.jsonl").write_text(json.dumps(header) + "\n")


def test_pi_continue_known_session(env):
    cfg, bin_dir, work = env
    fake(bin_dir, "pi", "")
    write_session(cfg, "abc123", work)
    r = run("pi", "again", work, cfg, "abc123")
    assert r.session == "abc123"
    argv = call(bin_dir, "pi")["argv"]
    assert argv[argv.index("--session-id") + 1] == "abc123"


def test_claude_env(env):
    cfg, bin_dir, work = env
    fake(bin_dir, "claude", f"sys.stdout.write(open({str(FIX / 'claude-run.json')!r}).read())\n")
    r = run("claude", "do it", work, cfg, None)
    c = call(bin_dir, "claude")
    assert c["env"]["ANTHROPIC_AUTH_TOKEN"] == "secret-token"
    assert "ANTHROPIC_API_KEY" not in c["env"]
    assert c["env"]["ANTHROPIC_BASE_URL"] == cfg.gateway
    assert c["env"]["ANTHROPIC_MODEL"] == cfg.model
    assert "secret-token" not in " ".join(c["argv"])
    assert "--resume" not in c["argv"]
    assert r.summary.startswith("모든 16개 테스트 통과") and r.session


def test_claude_continue_uses_resume(env):
    cfg, bin_dir, work = env
    fake(bin_dir, "claude", "")
    r = run("claude", "again", work, cfg, "sess-1")
    argv = call(bin_dir, "claude")["argv"]
    assert argv[argv.index("--resume") + 1] == "sess-1"
    assert r.session == "sess-1"


def test_timeout(env):
    cfg, bin_dir, work = env
    cfg.timeout = 1
    fake(bin_dir, "pi", "time.sleep(5)\n")
    r = run("pi", "slow", work, cfg, None)
    assert r.status == "timeout" and r.exit_code is None
    assert r.log_path.exists()


def test_nonzero_exit(env):
    cfg, bin_dir, work = env
    fake(bin_dir, "pi", "sys.exit(7)\n")
    r = run("pi", "x", work, cfg, None)
    assert (r.status, r.exit_code) == ("failed", 7)


def test_missing_executable(env):
    cfg, bin_dir, work = env
    with pytest.raises(PreflightError):
        run("pi", "x", work, cfg, None, which=lambda name: None)


@pytest.mark.parametrize("given", ["abc", "2026", "abc123-x"])
def test_pi_continue_needs_exact_id(env, given):
    cfg, bin_dir, work = env
    fake(bin_dir, "pi", "")
    write_session(cfg, "abc123", work)
    with pytest.raises(UnknownSession):
        run("pi", "again", work, cfg, given)
    assert not (bin_dir / "pi.call").exists()


def test_pi_continue_other_folder(env, tmp_path):
    cfg, bin_dir, work = env
    fake(bin_dir, "pi", "")
    other = tmp_path / "other"
    other.mkdir()
    write_session(cfg, "abc123", other)
    with pytest.raises(UnknownSession):
        run("pi", "again", work, cfg, "abc123")


def test_terminate_stops_worker_and_reports(tmp_path):
    """Killing local-agent (e.g. a shell tool time limit) must stop the worker and still print a report."""
    import signal, subprocess, sys, time
    home = tmp_path / "home"; home.mkdir(); (home / "token").write_text("t\n")
    bin_dir = tmp_path / "bin"
    fake(bin_dir, "pi", "open('made.py', 'w').write('x')\ntime.sleep(30)\n")
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    driver = (
        "import sys; sys.path.insert(0, %r)\n"
        "from local_agent import cli\n"
        "cli.check = lambda cfg: None\n"
        "sys.exit(cli.main(['--dir', %r, 'x']))\n"
    ) % (str(Path(__file__).resolve().parent.parent / "src"), str(repo))
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}", LOCAL_AGENT_HOME=str(home),
               XDG_STATE_HOME=str(tmp_path / "state"))
    proc = subprocess.Popen([sys.executable, "-c", driver], env=env, stdout=subprocess.PIPE, text=True)
    for _ in range(100):
        if (bin_dir / "pi.call").exists():
            break
        time.sleep(0.1)
    time.sleep(0.3)
    proc.send_signal(signal.SIGTERM)
    out, _ = proc.communicate(timeout=10)
    assert proc.returncode == 5
    assert out.startswith("status: interrupted\n")
    assert "made.py" in out.split("new files:")[1]
    worker = call(bin_dir, "pi")["pid"]
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(worker, 0)
