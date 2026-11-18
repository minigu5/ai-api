# ai_api

학교 Mac mini 클러스터의 로컬 모델을 Claude Code·Codex의 하위 작업자로 쓰는 `local-agent` 명령.

- 설치·업데이트(같은 명령): `curl -fsSL https://raw.githubusercontent.com/minigu5/ai-api/main/scripts/get.sh | sh` (`~/.local/share/ai-api`에 받아 `scripts/install.sh` 실행; 저장소가 public일 때만 됨) — 링크 설치 후 토큰을 한 번 물어봄(CA·`models.json`은 자동 생성). Apple Silicon Mac에서 Python 3.12·Node 22·`pi` 1.0.0을 `~/.local/share/ai-api-runtime`에 관리자 권한 없이 함께 설치(체크섬 검증). 학교망(또는 Tailscale) 필요. 설정만 다시: `local-agent --setup`
- 토큰은 클러스터 주인에게 받기 (`omm cluster token add <name>`)
- 사용: `local-agent --dir <저장소> "<지시문>"`, 이어서 `local-agent --continue <session> "<추가 지시>"`
- Codex: `docs/codex-agents-snippet.md`를 AGENTS.md에 붙여 넣기
- 테스트: `.venv/bin/python -m pytest -q`
