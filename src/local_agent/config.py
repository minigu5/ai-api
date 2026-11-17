"""Where local-agent finds the cluster gateway, its credentials and its own state."""
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_GATEWAY = "https://10.80.118.138:52440"
DEFAULT_MODEL = "mlx-community/Qwen3.6-35B-A3B-8bit"
DEFAULT_TIMEOUT = 1800


@dataclass
class Config:
    gateway: str
    model: str
    home: Path
    token_path: Path
    ca_path: Path
    pi_dir: Path
    state_dir: Path
    timeout: int


def load_config(env: Mapping[str, str], model: str | None = None, timeout: int | None = None) -> Config:
    user_home = Path(env.get("HOME") or Path.home())
    home = Path(env["LOCAL_AGENT_HOME"]) if env.get("LOCAL_AGENT_HOME") else user_home / ".config" / "ai_api"
    state_root = Path(env["XDG_STATE_HOME"]) if env.get("XDG_STATE_HOME") else user_home / ".local" / "state"
    return Config(
        gateway=(env.get("LOCAL_AGENT_GATEWAY") or DEFAULT_GATEWAY).rstrip("/"),
        model=model or env.get("LOCAL_AGENT_MODEL") or DEFAULT_MODEL,
        home=home,
        token_path=home / "token",
        ca_path=home / "ca.pem",
        pi_dir=home / "pi",
        state_dir=state_root / "local-agent",
        timeout=timeout or DEFAULT_TIMEOUT,
    )
