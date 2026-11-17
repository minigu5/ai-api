"""Check the gateway answers, accepts our token and serves the model before any work starts."""
import json
import ssl
import urllib.error
import urllib.request

from .config import Config


class PreflightError(Exception):
    """One-line cause plus the command that shows or fixes it."""


def read_token(cfg: Config) -> str:
    try:
        return cfg.token_path.read_text().strip()
    except FileNotFoundError:
        raise PreflightError(
            f"no gateway token at {cfg.token_path}; on the head Mac run: omm cluster token add <name>"
        ) from None


def _ssl_context(cfg: Config) -> ssl.SSLContext | None:
    return ssl.create_default_context(cafile=str(cfg.ca_path)) if cfg.ca_path.exists() else None


def check(cfg: Config, opener=urllib.request.urlopen) -> None:
    token = read_token(cfg)
    req = urllib.request.Request(cfg.gateway + "/v1/models", headers={"Authorization": f"Bearer {token}"})
    try:
        with opener(req, timeout=10, context=_ssl_context(cfg)) as resp:
            ids = {m.get("id") for m in json.load(resp).get("data", [])}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise PreflightError(
                f"gateway rejected the token in {cfg.token_path}; on the head Mac run: omm cluster token add <name>"
            ) from None
        raise PreflightError(f"gateway {cfg.gateway} answered HTTP {e.code}; on the head Mac run: omm cluster status") from None
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise PreflightError(f"cannot reach gateway {cfg.gateway} ({reason}); on the head Mac run: omm cluster status") from None
    if cfg.model not in ids:
        raise PreflightError(
            f"model {cfg.model} is not loaded; on the head Mac run: omm cluster load {cfg.model} --on node4"
        )
