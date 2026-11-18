"""First-time setup: token, gateway CA and pi's model list, so a new user only has to paste the token."""
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse

from .config import DEFAULT_MODEL, Config
from .preflight import PreflightError, check, served_models

PEM = re.compile(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----\n", re.S)
PI_PACKAGE = "@earendil-works/pi-coding-agent"


def fetch_ca(gateway: str, run=subprocess.run) -> str:
    """The gateway sends its own CA as the last certificate of the chain; take that one."""
    url = urlparse(gateway)
    out = run(["openssl", "s_client", "-connect", f"{url.hostname}:{url.port or 443}", "-showcerts"],
              input="", capture_output=True, text=True, timeout=15).stdout
    certs = PEM.findall(out)
    if not certs:
        raise PreflightError(f"cannot read a certificate from {gateway}; are you on the school network?")
    ca = certs[-1]
    info = run(["openssl", "x509", "-noout", "-subject", "-issuer"], input=ca, capture_output=True, text=True).stdout
    subject, _, issuer = info.partition("\n")
    if subject.removeprefix("subject=").strip() != issuer.removeprefix("issuer=").strip():
        raise PreflightError(f"{gateway} did not send its CA certificate; ask the cluster owner for ca.pem")
    return ca


def models_json(gateway: str, ids: list[str]) -> str:
    models = [{"id": i, "contextWindow": 262144, "maxTokens": 32000} for i in dict.fromkeys([DEFAULT_MODEL, *ids])]
    return json.dumps({"providers": {"cluster": {
        "baseUrl": gateway + "/v1", "api": "openai-completions",
        "apiKey": "!cat $HOME/.config/ai_api/token", "models": models}}}, indent=2) + "\n"


def setup(cfg: Config, env=os.environ, ask=getpass.getpass, run=subprocess.run, out=sys.stdout) -> None:
    cfg.home.mkdir(parents=True, exist_ok=True)
    if not cfg.token_path.exists():
        token = (env.get("LOCAL_AGENT_TOKEN") or ask("Gateway token (ask the cluster owner): ")).strip()
        if not token:
            raise PreflightError("no token given")
        cfg.token_path.write_text(token + "\n")
        cfg.token_path.chmod(0o600)
        print(f"wrote {cfg.token_path}", file=out)
    if not cfg.ca_path.exists():
        cfg.ca_path.write_text(fetch_ca(cfg.gateway, run))
        print(f"wrote {cfg.ca_path} (from {cfg.gateway})", file=out)
    check(cfg, model_ok=False)
    pi_models = cfg.pi_dir / "models.json"
    if not pi_models.exists():
        pi_models.parent.mkdir(parents=True, exist_ok=True)
        pi_models.write_text(models_json(cfg.gateway, served_models(cfg)))
        print(f"wrote {pi_models}", file=out)
    if shutil.which("pi") is None:
        print(f"missing: pi. install it with: npm install -g {PI_PACKAGE}", file=out)
        raise PreflightError("pi is not installed")
    check(cfg)
    print("ready: try  local-agent --dir <git repo> \"<task>\"", file=out)

