import io
import json
import urllib.error

import pytest

from local_agent.config import load_config
from local_agent.preflight import PreflightError, check

MODEL = "mlx-community/Qwen3.6-35B-A3B-8bit"


def make_cfg(tmp_path, **env):
    (tmp_path / "token").write_text("secret-token\n")
    return load_config({"LOCAL_AGENT_HOME": str(tmp_path), **env})


def models_response(*ids):
    return io.BytesIO(json.dumps({"data": [{"id": i} for i in ids]}).encode())


def test_defaults(tmp_path):
    cfg = load_config({"HOME": str(tmp_path)})
    assert cfg.gateway == "https://10.80.118.138:52440"
    assert cfg.model == MODEL
    assert cfg.timeout == 1800
    assert cfg.home == tmp_path / ".config" / "ai_api"
    assert cfg.pi_dir == cfg.home / "pi"
    assert cfg.token_path == cfg.home / "token"
    assert cfg.ca_path == cfg.home / "ca.pem"
    assert cfg.state_dir == tmp_path / ".local" / "state" / "local-agent"


def test_env_override(tmp_path):
    env = {"LOCAL_AGENT_GATEWAY": "https://gw:1", "LOCAL_AGENT_MODEL": "m-env",
           "LOCAL_AGENT_HOME": str(tmp_path), "XDG_STATE_HOME": str(tmp_path / "st")}
    cfg = load_config(env)
    assert (cfg.gateway, cfg.model, cfg.home) == ("https://gw:1", "m-env", tmp_path)
    assert cfg.state_dir == tmp_path / "st" / "local-agent"
    assert load_config(env, model="m-arg", timeout=5).model == "m-arg"
    assert load_config(env, timeout=5).timeout == 5


def test_missing_token_file(tmp_path):
    cfg = load_config({"LOCAL_AGENT_HOME": str(tmp_path)})
    with pytest.raises(PreflightError) as e:
        check(cfg, opener=lambda *a, **k: models_response(MODEL))
    assert str(tmp_path / "token") in str(e.value)


def test_gateway_unreachable(tmp_path):
    cfg = make_cfg(tmp_path)

    def opener(*a, **k):
        raise urllib.error.URLError("timed out")

    with pytest.raises(PreflightError) as e:
        check(cfg, opener=opener)
    assert cfg.gateway in str(e.value) and "omm cluster status" in str(e.value)


def test_bad_token(tmp_path):
    cfg = make_cfg(tmp_path)

    def opener(req, *a, **k):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    with pytest.raises(PreflightError) as e:
        check(cfg, opener=opener)
    assert "omm cluster token add" in str(e.value)


def test_model_not_loaded(tmp_path):
    cfg = make_cfg(tmp_path)
    with pytest.raises(PreflightError) as e:
        check(cfg, opener=lambda *a, **k: models_response("other"))
    assert f"omm cluster load {MODEL} --on node4" in str(e.value)


def test_ok(tmp_path):
    cfg = make_cfg(tmp_path)
    seen = {}

    def opener(req, *a, **k):
        seen["auth"] = req.get_header("Authorization")
        seen["url"] = req.full_url
        return models_response("x", MODEL)

    check(cfg, opener=opener)
    assert seen == {"auth": "Bearer secret-token", "url": cfg.gateway + "/v1/models"}
