import os
import subprocess
from pathlib import Path

import pytest

from local_agent import cli
from local_agent.preflight import PreflightError
from test_harness import FIX, call, fake

ROOT = Path(__file__).resolve().parent.parent


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "token").write_text("secret-token\n")
    bin_dir = tmp_path / "bin"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("LOCAL_AGENT_HOME", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(cli, "check", lambda cfg: None)
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "a.py").write_text("a = 1\n")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return bin_dir, repo


PI_WRITES_FILE = (
    "open('made.py', 'w').write('x = 1\\n')\n"
    f"sys.stdout.write(open({str(FIX / 'pi-run.jsonl')!r}).read())\n"
)


def test_report_ok(setup, capsys):
    bin_dir, repo = setup
    fake(bin_dir, "pi", PI_WRITES_FILE)
    assert cli.main(["--dir", str(repo), "do it"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("status: ok\n")
    heads = ["session:", "time:", "summary:", "changes:", "new files:", "log:"]
    positions = [out.index(h) for h in heads]
    assert positions == sorted(positions)
    assert "All 10 tests pass." in out
    assert "made.py" in out.split("new files:")[1]


def test_not_repo_exit2(setup, tmp_path, capsys):
    bin_dir, _ = setup
    fake(bin_dir, "pi", "")
    plain = tmp_path / "plain"
    plain.mkdir()
    assert cli.main(["--dir", str(plain), "x"]) == 2
    assert "not a git" in capsys.readouterr().err
    assert not (bin_dir / "pi.call").exists()


def test_preflight_fail_exit2(setup, monkeypatch, capsys):
    bin_dir, repo = setup
    fake(bin_dir, "pi", "")

    def fail(cfg):
        raise PreflightError("model X is not loaded; on the head Mac run: omm cluster load X --on node4")

    monkeypatch.setattr(cli, "check", fail)
    assert cli.main(["--dir", str(repo), "x"]) == 2
    err = capsys.readouterr().err
    assert err.strip().count("\n") == 0 and err.startswith("local-agent: model X is not loaded")
    assert not (bin_dir / "pi.call").exists()


def test_unknown_session_exit2(setup, capsys):
    bin_dir, repo = setup
    fake(bin_dir, "pi", "")
    assert cli.main(["--dir", str(repo), "--continue", "nope", "x"]) == 2
    assert "nope" in capsys.readouterr().err


def test_failed_worker_still_reports(setup, capsys):
    bin_dir, repo = setup
    fake(bin_dir, "pi", "open('made.py', 'w').write('x')\nsys.exit(7)\n")
    assert cli.main(["--dir", str(repo), "x"]) == 3
    out = capsys.readouterr().out
    assert out.startswith("status: failed (exit 7)\n")
    assert "made.py" in out.split("new files:")[1]
    assert "summary:\n(none)" in out


def test_timeout_exit4(setup, capsys):
    bin_dir, repo = setup
    fake(bin_dir, "pi", "time.sleep(5)\n")
    assert cli.main(["--dir", str(repo), "--timeout", "1", "x"]) == 4
    assert capsys.readouterr().out.startswith("status: timeout (1s)\n")


def test_harness_and_model_options(setup):
    bin_dir, repo = setup
    fake(bin_dir, "claude", "")
    cli.main(["--dir", str(repo), "--harness", "claude", "--model", "m2", "x"])
    assert call(bin_dir, "claude")["env"]["ANTHROPIC_MODEL"] == "m2"


def test_bin_wrapper(tmp_path):
    link = tmp_path / "local-agent"
    link.symlink_to(ROOT / "bin" / "local-agent")
    r = subprocess.run([str(link), "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--continue" in r.stdout


def test_dir_subfolder_is_worker_cwd(setup):
    bin_dir, repo = setup
    sub = repo / "pkg"
    sub.mkdir()
    fake(bin_dir, "pi", "")
    assert cli.main(["--dir", str(sub), "x"]) == 0
    assert os.path.realpath(call(bin_dir, "pi")["cwd"]) == os.path.realpath(sub)


def test_report_sections_are_capped(setup, capsys):
    bin_dir, repo = setup
    fake(bin_dir, "pi", "import os\nos.makedirs('gen')\n[open(f'gen/f{i}.txt', 'w').write('x') for i in range(100)]\n")
    assert cli.main(["--dir", str(repo), "x"]) == 0
    out = capsys.readouterr().out
    new_section = out.split("new files:\n")[1].split("\nlog:")[0].splitlines()
    assert len(new_section) <= 31
    assert "70 more" in new_section[-1]
