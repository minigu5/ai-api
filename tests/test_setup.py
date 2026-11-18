import json
from types import SimpleNamespace

import pytest

from local_agent import setup as su
from local_agent.config import DEFAULT_MODEL, load_config
from local_agent.preflight import PreflightError

LEAF = "-----BEGIN CERTIFICATE-----\nleaf\n-----END CERTIFICATE-----\n"
CA = "-----BEGIN CERTIFICATE-----\nca\n-----END CERTIFICATE-----\n"


def fake_run(subject="O=cluster CA", issuer="O=cluster CA"):
    def run(argv, input=None, **kw):
        if "s_client" in argv:
            return SimpleNamespace(stdout=f"junk\n{LEAF}more\n{CA}tail")
        return SimpleNamespace(stdout=f"subject={subject}\nissuer={issuer}\n")
    return run


def test_fetch_ca_takes_last_self_signed_cert():
    assert su.fetch_ca("https://10.0.0.1:52440", fake_run()) == CA


def test_fetch_ca_refuses_when_chain_has_no_root():
    with pytest.raises(PreflightError, match="ca.pem"):
        su.fetch_ca("https://10.0.0.1:52440", fake_run(issuer="O=someone else"))


def test_models_json_default_first_no_duplicates():
    data = json.loads(su.models_json("https://g:1", ["other", DEFAULT_MODEL]))["providers"]["cluster"]
    assert data["baseUrl"] == "https://g:1/v1"
    assert [m["id"] for m in data["models"]] == [DEFAULT_MODEL, "other"]


def test_setup_writes_files_and_needs_pi(tmp_path, monkeypatch):
    cfg = load_config({"LOCAL_AGENT_HOME": str(tmp_path / "cfg")})
    monkeypatch.setattr(su, "check", lambda cfg, **kw: None)
    monkeypatch.setattr(su, "served_models", lambda cfg: ["m1"])
    monkeypatch.setattr(su.shutil, "which", lambda name: None)
    out = []
    with pytest.raises(PreflightError, match="pi is not installed"):
        su.setup(cfg, env={}, ask=lambda prompt: " tok \n", run=fake_run(), out=SimpleNamespace(write=out.append))
    assert cfg.token_path.read_text() == "tok\n" and oct(cfg.token_path.stat().st_mode)[-3:] == "600"
    assert cfg.ca_path.read_text() == CA
    assert "m1" in (cfg.pi_dir / "models.json").read_text()
