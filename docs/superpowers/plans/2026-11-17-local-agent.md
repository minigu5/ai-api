# local-agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `local-agent "지시문"` 한 줄로 학교 클러스터의 로컬 모델(pi 기본)에게 저장소 수정을 맡기고, 짧은 보고만 돌려받는다.

**Architecture:** 표준 라이브러리만 쓰는 Python 패키지 `src/local_agent/`. 사전 점검(게이트웨이·모델) → 작업 전 git 스냅샷 → 작업자 실행(pi 또는 claude -p, 전체 로그는 파일) → 스냅샷 대비 변경 보고. 메인테이너용 Claude Code 스킬과 Codex 지침 조각을 함께 둔다.

**Tech Stack:** Python 3.12+ 표준 라이브러리(argparse, subprocess, urllib, ssl, json, uuid), pytest(개발용 `.venv`), git, pi 1.0.0, Claude Code CLI.

**Spec:** `docs/superpowers/specs/2026-11-17-local-agent-design.md`

## Global Constraints

- 런타임 의존성 없음(표준 라이브러리만). pytest는 `.venv`에만.
- 기본값: harness `pi`, model `mlx-community/Qwen3.6-35B-A3B-8bit`, gateway `https://10.80.118.138:52440`, token `~/.config/ai_api/token`, CA `~/.config/ai_api/ca.pem`, pi 설정 디렉터리 `~/.config/ai_api/pi`, pi provider 이름 `cluster`.
- 환경변수로 덮어쓰기: `LOCAL_AGENT_GATEWAY`, `LOCAL_AGENT_MODEL`, `LOCAL_AGENT_HOME`(기본 `~/.config/ai_api`).
- 사용자 `~/.pi`·`~/.claude` 설정은 건드리지 않는다(pi는 `PI_CODING_AGENT_DIR`, claude는 환경변수만).
- 작업자는 커밋하지 않는다. `--dir`이 git 작업 트리가 아니면 거부.
- 토큰은 출력·로그·명령행 인자에 절대 넣지 않는다(환경변수/파일로만 전달).
- 지시문은 셸 문자열로 조립하지 않고 argv로 전달.
- 상태 저장: `~/.local/state/local-agent/`(`logs/`, `sessions/`). `XDG_STATE_HOME`이 있으면 그 아래.
- 시간 제한 기본 1800초(`--timeout`).
- 종료 코드: 0 작업자 정상 종료, 2 사전 점검 실패(게이트웨이/인증/모델/저장소), 3 작업자 비정상 종료, 4 시간 초과.

## Review Focus

1. 이미 수정 중인(더러운) 저장소에서 실행 → 보고에는 이번 실행이 바꾼 것만 나와야 한다. (Task 2 테스트)
2. 작업자가 실패하거나 시간 초과돼도 그때까지의 변경 보고와 로그 경로는 출력돼야 한다. (Task 4 테스트)
3. 게이트웨이 꺼짐 / 토큰 틀림 / 모델 미로드 → 한 줄 원인 + 확인 명령, 종료 코드 2, 작업자 실행 안 함. (Task 1 테스트)
4. 따옴표·줄바꿈·`$()`가 든 지시문이 그대로 작업자에게 전달돼야 한다. (Task 3 테스트)
5. 없는 세션 ID로 `--continue` → 새 세션을 조용히 만들지 말고 오류(종료 2). (Task 3 테스트)

---

### Task 1: 설정과 사전 점검

**Files:**
- Create: `src/local_agent/__init__.py`, `src/local_agent/config.py`, `src/local_agent/preflight.py`
- Create: `tests/conftest.py`(sys.path에 `src` 추가), `tests/test_preflight.py`
- Create: `.gitignore`(`.venv/`, `__pycache__/`, `.pytest_cache/`)

**Interfaces:**
- Produces:
  - `@dataclass Config: gateway: str; model: str; home: Path; token_path: Path; ca_path: Path; pi_dir: Path; state_dir: Path; timeout: int`
  - `load_config(env: Mapping[str,str], model: str|None=None, timeout: int|None=None) -> Config`
  - `class PreflightError(Exception)` — `str(e)`는 한 줄 원인 + 확인 명령
  - `check(cfg: Config, opener=urllib.request.urlopen) -> None` — `GET {gateway}/v1/models`(Authorization: Bearer, CA 고정 ssl context, 10초) 후 `cfg.model`이 `data[].id`에 있는지 확인
  - `read_token(cfg) -> str`

- [ ] **Step 1: 실패하는 테스트 작성** (`opener`에 가짜 함수 주입)
  - `test_defaults`: 빈 env → `gateway == "https://10.80.118.138:52440"`, `model == "mlx-community/Qwen3.6-35B-A3B-8bit"`, `timeout == 1800`, `pi_dir == home/"pi"`.
  - `test_env_override`: `LOCAL_AGENT_GATEWAY`, `LOCAL_AGENT_MODEL`, `LOCAL_AGENT_HOME` 반영; 인자 `model=`이 env보다 우선.
  - `test_missing_token_file`: 토큰 파일 없음 → `PreflightError`, 메시지에 토큰 경로 포함.
  - `test_gateway_unreachable`: opener가 `URLError` → 메시지에 `gateway` 주소와 `omm cluster status` 포함.
  - `test_bad_token`: opener가 `HTTPError(401)` → 메시지에 `omm cluster token add` 포함.
  - `test_model_not_loaded`: 응답 `{"data":[{"id":"other"}]}` → 메시지에 `omm cluster load mlx-community/Qwen3.6-35B-A3B-8bit --on node4` 포함.
  - `test_ok`: 응답에 모델 id 있음 → 예외 없음, 요청 헤더에 Bearer 토큰.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_preflight.py -q` → FAIL(import 오류)
- [ ] **Step 3:** `config.py`, `preflight.py` 구현
- [ ] **Step 4:** 같은 명령 → 7 passed
- [ ] **Step 5:** 커밋 `feat: config and gateway preflight`

### Task 2: 작업 전후 저장소 비교

**Files:**
- Create: `src/local_agent/workspace.py`, `tests/test_workspace.py`

**Interfaces:**
- Produces:
  - `class NotARepo(Exception)`
  - `@dataclass Snapshot: root: Path; base: str; untracked: frozenset[str]`
  - `snapshot(dir: Path) -> Snapshot` — `git rev-parse --show-toplevel`(실패 시 `NotARepo`), `base = git stash create` 결과(비어 있으면 `HEAD`), `untracked = git ls-files --others --exclude-standard`
  - `changes(s: Snapshot) -> tuple[str, list[str]]` — (`git diff --stat <base>` 출력, 이번에 새로 생긴 미추적 파일 정렬 목록)

`git stash create`는 작업 트리를 건드리지 않고 현재 수정 상태의 커밋 객체만 만든다 → 실행 전 수정분은 diff에서 빠진다.

- [ ] **Step 1: 실패하는 테스트 작성** (`tmp_path`에 `git init` + 커밋 하나)
  - `test_not_a_repo`: 빈 폴더 → `NotARepo`.
  - `test_clean_repo_changes`: 스냅샷 후 기존 파일 수정 + 새 파일 → stat에 수정 파일명, 새 파일 목록 == `["new.py"]`.
  - `test_dirty_repo_excludes_prior_edits`: 스냅샷 전 `a.py` 수정 + 미추적 `old.txt`; 스냅샷 후 `b.py`만 수정 → stat에 `b.py` 있고 `a.py` 없음, 새 파일에 `old.txt` 없음.
  - `test_snapshot_does_not_touch_tree`: 스냅샷 전후 `git status --porcelain` 동일.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_workspace.py -q` → FAIL
- [ ] **Step 3:** 구현(subprocess, `cwd=dir`, `check=True`, text)
- [ ] **Step 4:** → 4 passed
- [ ] **Step 5:** 커밋 `feat: git snapshot and change report`

### Task 3: 작업자 실행기 (pi, claude)

**Files:**
- Create: `src/local_agent/harness.py`, `tests/test_harness.py`
- Use: `tests/fixtures/pi-run.jsonl`(실제 pi `--mode json` 출력, message_end만 남김), `tests/fixtures/claude-run.json`(실제 `claude -p --output-format json` 출력)

**Interfaces:**
- Consumes: `Config`, `read_token` (Task 1)
- Produces:
  - `@dataclass RunResult: status: Literal["ok","failed","timeout"]; exit_code: int|None; summary: str; session: str; log_path: Path`
  - `class UnknownSession(Exception)`
  - `run(harness: Literal["pi","claude"], prompt: str, cwd: Path, cfg: Config, session: str|None, *, which=shutil.which) -> RunResult`
  - `pi_summary(jsonl_text: str) -> str` — 마지막 `message_end`(role assistant)의 `type=="text"` 내용들을 이어 붙여 strip
  - `claude_summary(json_text: str) -> tuple[str, str]` — (`result` strip, `session_id`)

실행 규칙:
- 공통: `subprocess.run(argv, cwd=cwd, stdin=DEVNULL, stdout=로그파일, stderr=로그파일.err, timeout=cfg.timeout, env=…)`; 로그 `state_dir/logs/<YYYYmmdd-HHMMSS>-<harness>.log`. 시간 초과면 `status="timeout"`, `exit_code=None`. 작업자 실행 파일이 없으면(`which`가 None) `PreflightError`.
- pi: 새 세션이면 `session = uuid4()`. `--continue`인데 `state_dir/sessions/` 아래(하위 폴더 포함) 파일명에 그 ID가 들어간 파일이 없으면 `UnknownSession`. argv `["pi","-p","--mode","json","--model",f"cluster/{cfg.model}","--session-dir",str(state_dir/"sessions"),"--session-id",session,prompt]`; env 추가 `PI_CODING_AGENT_DIR=cfg.pi_dir`, `PI_OFFLINE=1`, `PI_SKIP_VERSION_CHECK=1`, `NODE_EXTRA_CA_CERTS=cfg.ca_path`.
- claude: argv `["claude","-p",prompt,"--output-format","json","--dangerously-skip-permissions"]` + `--continue`면 `["--resume",session]`; env 추가 `ANTHROPIC_BASE_URL=cfg.gateway`, `ANTHROPIC_AUTH_TOKEN=<토큰>`, `ANTHROPIC_MODEL`/`ANTHROPIC_SMALL_FAST_MODEL=cfg.model`, `NODE_EXTRA_CA_CERTS`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`; env에서 `ANTHROPIC_API_KEY` 제거. 세션 ID는 출력 JSON의 `session_id`. 존재하지 않는 `--resume` ID는 claude가 오류로 끝나므로 `status="failed"`로 보고(별도 검사 없음).

- [ ] **Step 1: 실패하는 테스트 작성** (가짜 `pi`/`claude` 실행 파일을 `tmp_path/bin`에 만들고 `PATH` 앞에 둠; 가짜는 받은 argv와 일부 env를 파일에 기록하고 fixture 내용을 stdout으로 출력)
  - `test_pi_summary_fixture`: `pi_summary(fixture)`가 `"All 10 tests pass."`로 시작.
  - `test_claude_summary_fixture`: `claude_summary(fixture)` → 요약이 `"모든 16개 테스트 통과"`로 시작, session 비어 있지 않음.
  - `test_pi_argv_and_env`: 기록된 argv에 `--session-id`, `cluster/<model>`, 마지막 인자가 지시문 그대로; env `PI_CODING_AGENT_DIR == cfg.pi_dir`; 토큰 문자열이 argv에 없음.
  - `test_prompt_passed_verbatim`: 지시문 `'say "hi"\nline2 $(rm -rf x)'` → 가짜가 기록한 마지막 argv와 바이트 단위로 같음.
  - `test_pi_continue_unknown_session`: 없는 ID → `UnknownSession`, 가짜 pi는 실행되지 않음.
  - `test_claude_env`: env에 `ANTHROPIC_AUTH_TOKEN`은 토큰 파일 값, `ANTHROPIC_API_KEY` 없음, argv에 토큰 없음.
  - `test_timeout`: 가짜가 `sleep 5`, `cfg.timeout=1` → `status=="timeout"`, 로그 파일 존재.
  - `test_nonzero_exit`: 가짜가 `exit 7` → `status=="failed"`, `exit_code==7`.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_harness.py -q` → FAIL
- [ ] **Step 3:** 구현
- [ ] **Step 4:** → 8 passed
- [ ] **Step 5:** 커밋 `feat: pi and claude harness runners`

### Task 4: 명령행과 보고 형식

**Files:**
- Create: `src/local_agent/cli.py`, `src/local_agent/__main__.py`, `bin/local-agent`(실행 가능한 sh: 저장소 `src`를 `PYTHONPATH`에 넣고 `python3 -m local_agent "$@"`; 심볼릭 링크로 불려도 `realpath`로 저장소를 찾음)
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1~3 전부
- Produces: `main(argv: list[str]|None=None) -> int`

인자: `prompt`(위치, 필수), `--dir`(기본 현재 폴더), `--model`, `--harness {pi,claude}`(기본 pi), `--continue SESSION`, `--timeout SECONDS`.
순서: config → 저장소 확인(`snapshot`; `NotARepo`면 종료 2) → `check` → `run` → `changes` → 보고 출력.

보고 형식(표준출력, 이 순서와 머리말 그대로):
```
status: ok            # 또는 "failed (exit 7)" / "timeout (1800s)"
session: <id>         # 다음 지시: local-agent --continue <id> "..."
time: 158s
summary:
<작업자 요약, 비어 있으면 "(none)">
changes:
<git diff --stat, 없으면 "(none)">
new files:
<한 줄에 하나, 없으면 "(none)">
log: <로그 경로>
```
사전 점검 실패는 표준오류에 `local-agent: <원인>` 한 줄, 종료 2.

- [ ] **Step 1: 실패하는 테스트 작성** (`check`는 monkeypatch로 통과/실패 주입, 작업자는 Task 3 방식의 가짜 실행 파일)
  - `test_report_ok`: 정상 → 종료 0, 출력이 `status: ok`로 시작, `session:`·`time:`·`summary:`·`changes:`·`new files:`·`log:` 순서대로 존재, 가짜가 만든 파일이 `new files`에 나옴.
  - `test_not_repo_exit2`: git 아닌 폴더 → 종료 2, stderr에 `not a git`, 작업자 실행 안 됨.
  - `test_preflight_fail_exit2`: `check`가 `PreflightError("model X is not loaded…")` → 종료 2, stderr 한 줄.
  - `test_failed_worker_still_reports`: 가짜가 파일을 만들고 `exit 7` → 종료 3, `status: failed (exit 7)`, 그 파일이 `new files`에 나옴.
  - `test_timeout_exit4`: → 종료 4, `status: timeout (1s)`.
  - `test_bin_wrapper`: `bin/local-agent --help` 실행 → 종료 0, 출력에 `--continue`.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_cli.py -q` → FAIL
- [ ] **Step 3:** 구현
- [ ] **Step 4:** `.venv/bin/python -m pytest -q` → 전부 통과
- [ ] **Step 5:** 커밋 `feat: local-agent command and report`

### Task 5: 메인테이너 지침, 설치, 실제 클러스터 확인

**Files:**
- Create: `skills/local-agent/SKILL.md`(Claude Code 스킬), `docs/codex-agents-snippet.md`(Codex AGENTS.md에 붙일 같은 내용), `README.md`(설치·사용 5줄)
- Create: `scripts/install.sh` — `~/.local/bin/local-agent` → `bin/local-agent` 심볼릭 링크, `~/.claude/skills/local-agent` → `skills/local-agent` 심볼릭 링크. 이미 있으면 같은 대상일 때만 넘어가고, 다른 것이면 멈추고 알림.

SKILL.md 내용(frontmatter `name: local-agent`, description: "코드 수정·탐색 작업을 학교 클러스터 로컬 모델에 맡겨 Claude 토큰을 아낄 때"):
1. 맡길 일: 여러 파일 읽기·수정, 테스트 작성, 반복 수정. 맡기지 말 일: 비밀값 다루기, 커밋·푸시, 설계 결정.
2. 지시문 쓰기: 목표, 받아들일 조건(실행할 테스트 명령 포함), 건드릴 파일/건드리지 말 파일, "끝나면 짧게 요약".
3. 실행: `local-agent --dir <repo> "<지시문>"`(Bash, 시간 제한 넉넉히 30분).
4. 검증: 보고의 `changes`로 범위 확인 → 필요한 파일만 `git diff -- <file>` → 테스트를 직접 실행. 작업자 요약은 믿지 말 것(시험에서 거짓 "통과" 보고 확인됨).
5. 부족하면 `local-agent --continue <session> "<구체적 수정 지시>"`; 3번 넘게 실패하면 직접 하거나 사용자에게 보고.
6. 통과하면 메인테이너가 커밋.
7. 종료 코드 2면 보고된 확인 명령을 사용자에게 전달.

- [ ] **Step 1:** 위 파일 작성, `bash -n scripts/install.sh`
- [ ] **Step 2:** `scripts/install.sh` 실행 → `ls -l ~/.local/bin/local-agent ~/.claude/skills/local-agent`가 저장소를 가리킴
- [ ] **Step 3: 실제 확인** — 시험 과제 사본(`scratchpad/spike/template` 복사본, git 저장소)에서 `local-agent --dir <사본> "Read TASK.md and implement everything it asks. Run: python -m pytest -q"` (PATH에 pytest 있는 venv). 기대: 종료 0, 보고 형식대로, 숨김 테스트 통과 수 기록.
- [ ] **Step 4: 이어서 지시 확인** — 같은 사본에 `--continue <session> "Also add a test that ids stay unique after save/load when the highest id was removed."` → 종료 0, 같은 session.
- [ ] **Step 5: 사전 점검 확인** — `LOCAL_AGENT_MODEL=nope local-agent --dir <사본> "x"` → 종료 2, 한 줄 원인.
- [ ] **Step 6:** 커밋 `feat: maintainer skill, codex snippet, installer`
