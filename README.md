# ai_api

학교 Mac mini 클러스터의 로컬 모델을 Claude Code·Codex의 하위 작업자로 쓰는 `local-agent` 명령.

- 설치: `scripts/install.sh` (`~/.local/bin/local-agent`, `~/.claude/skills/local-agent` 링크)
- 준비물: `~/.config/ai_api/token`(게이트웨이 토큰), `~/.config/ai_api/ca.pem`, `~/.config/ai_api/pi/models.json`, `pi`
- 사용: `local-agent --dir <저장소> "<지시문>"`, 이어서 `local-agent --continue <session> "<추가 지시>"`
- Codex: `docs/codex-agents-snippet.md`를 AGENTS.md에 붙여 넣기
- 테스트: `.venv/bin/python -m pytest -q`
