---
name: agentthread-ssh-screenshot
description: |
  SSH로 원격 서버에 명령어를 실행하고 결과를 교육용 터미널 스타일 PNG로 저장하는 스킬.
  "matter 서버에서 docker ps 실행하고 스크린샷 저장해줘", "서버 상태 확인하고 캡처해",
  "SSH 명령 실행 결과를 이미지로 남겨줘", "터미널 스크린샷 찍어줘" 같은 요청에
  반드시 이 스킬을 사용한다. 명령어 + 스크린샷 저장이 조금이라도 언급되면 우선 적용한다.
---

# SSH 명령 실행 & 터미널 스크린샷 저장 스킬

## 개요

원격 서버에 SSH로 명령어를 실행하고, 결과를 **macOS 터미널 스타일 PNG 이미지**로 렌더링하여
프로젝트 폴더에 저장한다. 명령이 여러 개면 순차 실행하고 명령마다 별도 PNG를 저장한다.

스크린샷은 교육용 목적에 맞게 실제 SSH 세션처럼 보여야 한다:
- 상단에 macOS 신호등 버튼 + 창 제목 (`user@hostname: ~`)
- 초록 `user@hostname` + 파란 `/current/path` + `$ 명령어` 프롬프트
- 명령 출력 결과

렌더링은 `run_command_with_screenshot` **대신** Python 스크립트로 수행한다.
(iTerm2 스크린샷은 창 전체를 캡처해 내용이 작게 찍히는 문제가 있음)

---

## 의존 도구

- `mcp__iterm2__run_command` — SSH 명령 실행 및 출력 캡처
- `mcp__iterm2__list_sessions` — 로컬 세션 찾기
- `mcp__workspace__bash` — Python 스크립트로 PNG 렌더링 및 파일 이름 결정
- `render_terminal.py` — 이 스킬 폴더의 `scripts/render_terminal.py`

---

## 설정 관리 (Configuration)

이 스킬은 서버별 연결 설정을 `<스킬 경로>/config.json`에 저장하여 영구 관리할 수 있다.

### 1. 설정 파일 경로
- 파일명: `config.json`
- 위치: `agentthread-ssh-screenshot` 스킬 디렉토리 내부 (예: `/Volumes/Data01/Users/yarang/.gemini/config/skills/agentthread-ssh-screenshot/config.json`)

### 2. 설정 파일 구조
```json
{
  "servers": {
    "<서버명>": {
      "host": "<실제 호스트명 또는 IP 또는 SSH alias>",
      "user": "<로그인 사용자명>",
      "cwd": "<기본 작업 디렉토리>"
    }
  }
}
```

### 3. 설정 변경 명령 처리
사용자가 설정을 변경해달라고 하거나 (예: `"matter 서버 설정을 host=192.168.1.10, user=deploy, cwd=/var/www/html로 등록해줘"`), 실행 시점에 설정을 커스텀하고 싶어 하는 경우:
1. `config.json`을 읽거나 없다면 새로 생성한다.
2. 지정된 서버명의 `host`, `user`, `cwd` 값을 추가/업데이트한다.
3. 수정된 내용을 다시 `config.json`에 JSON 포맷으로 저장한다.
4. "설정 저장 완료" 메시지와 함께 업데이트된 내용을 보고한다.

---

## 전체 워크플로우

### 1단계: 요청 파싱 및 설정 로드

대화에서 추출:
- **서버명**: SSH config 호스트명 (예: `matter`)
- **명령어 목록**: 실행 순서대로
- **저장 경로**: 미지정이면 현재 마운트된 프로젝트 폴더 사용

또한, `<스킬 경로>/config.json` 파일이 존재하는지 확인하고, 해당 파일에 해당 서버명에 대한 설정(`host`, `user`, `cwd`)이 있는지 로드한다.

### 2단계: 로컬 iTerm 세션 선택

`mcp__iterm2__list_sessions`로 세션 목록을 가져온다.
이름에 `(ssh)` 또는 `@`가 **없는** 세션 = 로컬 세션.
없으면 `mcp__iterm2__create_session`으로 생성한다.

### 3단계: 명령어별 반복

각 명령마다 아래 a~e를 수행한다.

#### a) 대기 시간 추정

| 유형 | 예시 | wait_seconds |
|------|------|-------------|
| 즉시 | `echo`, `hostname`, `uname`, `whoami` | 5 |
| 빠름 | `df -h`, `free -h`, `ls`, `ps`, `uptime` | 8 |
| 보통 | `docker ps`, `systemctl status`, `curl`, `ss` | 12 |
| 느림 | `docker compose logs`, `journalctl` | 20 |
| 매우 느림 | `apt install`, `docker pull`, `docker build` | 120+ |

#### b) SSH 실행 및 출력 캡처

**로컬 세션**에서 실행한다. 프롬프트 줄은 `render_terminal.py`가 생성하므로 SSH 명령은 **순수 출력만** 캡처하면 된다. 이스케이프가 필요 없다.

설정(`config.json`)을 기반으로 SSH 명령을 빌드한다:
- **대상 호스트/사용자**: `config.json`에 `user`와 `host`가 정의되어 있으면 `ssh <user>@<host>` 형식으로 실행한다. 없으면 사용자의 서버명 입력을 그대로 사용하여 `ssh <서버명>`으로 실행한다.
- **작업 디렉토리(cwd)**: `config.json`에 `cwd`가 정의되어 있으면 명령어 앞에 `cd <cwd> && `를 붙여 실행하여 설정된 디렉토리에서 작업이 수행되도록 한다. (예: `cd /var/www/html && docker ps`)

```
# 예시 (설정이 로드된 경우)
mcp__iterm2__run_command(
  command      = 'ssh <user>@<host> "cd <cwd> && <명령어> 2>&1"',
  session_id   = <로컬 세션 ID>,
  wait_seconds = <추정값>
)
```

결과로 반환되는 `result` 문자열에서 **유효한 출력 부분만 추출**한다.
(iTerm 히스토리가 섞여 있을 수 있으므로 맨 마지막 프롬프트 이후 내용을 사용)

#### c) topic 자동 생성

명령어에서 의미 있는 키워드를 추출해 하이픈 구분, 소문자, 최대 30자.

| 명령어 | topic |
|--------|-------|
| `docker ps` | `docker-ps` |
| `docker compose ps` | `docker-compose-ps` |
| `df -h` | `disk-usage` |
| `free -h` | `memory-usage` |
| `systemctl status nginx` | `nginx-status` |
| `docker compose logs app` | `app-logs` |
| `uname -a` | `system-info` |
| `curl -s http://localhost:8065/api/v4/system/ping` | `api-ping` |
| `ss -tlnp` | `open-ports` |
| `journalctl -u nginx` | `nginx-journal` |

규칙: 서비스/파일명 우선, 옵션 플래그 제외, URL은 핵심 단어만.

#### d) nnn 자동 증가

파일명 형식: `YYYY-MM-DD-NNN-{topic}.png`
날짜 → 번호 순으로 정렬되어 `ls` 결과가 시간순으로 항상 올바르게 정렬된다.

```bash
LAST=$(ls <저장경로>/<TODAY>-*-<topic>.png 2>/dev/null \
       | sed 's/.*-\([0-9]\{3\}\)-[^-]*\.png$/\1/' | sort -n | tail -1)
NNN=$(printf "%03d" $(( ${LAST:-0} + 1 )))
```

#### e) PNG 렌더링 (핵심 단계)

**`run_command_with_screenshot` 대신** `render_terminal.py`를 사용해 PNG를 직접 생성한다.
`--hostname`과 `--cmd`를 지정하면 스크립트가 자동으로 컬러 프롬프트 줄을 앞에 추가한다.

```bash
SCRIPT="<스킬 경로>/scripts/render_terminal.py"
OUTPUT="<저장경로>/<TODAY>-<NNN>-<topic>.png"

python3 "$SCRIPT" \
  --output   "$OUTPUT" \
  --hostname "<설정된 host 또는 서버 별칭>" \
  --user     "<설정된 user 또는 ubuntu>" \
  --cwd      "<설정된 cwd 또는 ~>" \
  --cmd      "<실행한 명령어>" \
  --width    920 \
  --font-size 15 \
  --text     '<b단계에서 캡처한 순수 출력 텍스트>'
```

- `--hostname` : `config.json`에 설정된 `host` (없으면 서버명)
- `--user`     : `config.json`에 설정된 `user` (없으면 `ubuntu` 기본값)
- `--cwd`      : `config.json`에 설정된 `cwd` (없으면 `~` 기본값)
- `--text`     : 명령 출력만 전달하면 됨. 프롬프트 줄은 스크립트가 자동 생성

> **스크립트 경로 확인**: 이 스킬의 SKILL.md 위치에서 `scripts/render_terminal.py`를 찾는다.
> 경로가 확실하지 않으면 `mcp__workspace__bash`로 `find` 명령으로 확인한다.

### 4단계: 결과 보고

저장된 파일 목록을 요약한다:

```
✅ 터미널 스크린샷 저장 완료 (2개)
  - 2026-05-20-001-docker-ps.png  (920×288)
  - 2026-05-20-002-disk-usage.png (920×192)
```

---

## 사용 예시

### 예시 1: 설정을 통해 실행 및 캡처

**요청**: "matter 서버에서 docker ps랑 df -h 실행하고 스크린샷 저장해줘" (단, `config.json`에 `matter` 설정이 다음과 같이 등록되어 있다고 가정)
```json
{
  "servers": {
    "matter": {
      "host": "10.0.0.5",
      "user": "deploy",
      "cwd": "/var/www/html"
    }
  }
}
```

**처리 순서**:

1. 서버: `matter`, 명령어: `["docker ps", "df -h"]`
2. 로컬 세션 ID 확인 (예: `E16AE72E`)
3. `config.json` 로드 완료: `host=10.0.0.5`, `user=deploy`, `cwd=/var/www/html`
4. **명령 1** — `docker ps`

   ```bash
   # 실행 (설정된 user, host, cwd 적용)
   ssh deploy@10.0.0.5 "cd /var/www/html && docker ps 2>&1"

   # PNG 렌더링 (설정된 값 적용)
   python3 render_terminal.py \
     --hostname 10.0.0.5 --user deploy --cwd /var/www/html --cmd "docker ps" \
     --text "<캡처된 출력>" --output 2026-05-20-001-docker-ps.png
   ```

5. **명령 2** — `df -h`

   ```bash
   ssh deploy@10.0.0.5 "cd /var/www/html && df -h 2>&1"

   python3 render_terminal.py \
     --hostname 10.0.0.5 --user deploy --cwd /var/www/html --cmd "df -h" \
     --text "<캡처된 출력>" --output 2026-05-20-002-disk-usage.png
   ```

6. 결과 보고

### 예시 2: 서버 설정 등록/변경

**요청**: "matter 서버 설정을 host=192.168.1.5, user=admin, cwd=/var/www로 등록해줘"

**처리 순서**:

1. `<스킬 경로>/config.json` 파일 읽기 또는 생성
2. 아래와 같이 JSON 업데이트 후 저장:
   ```json
   {
     "servers": {
       "matter": {
         "host": "192.168.1.5",
         "user": "admin",
         "cwd": "/var/www"
       }
     }
   }
   ```
3. 완료 메시지 보고

---

## 주의사항

- `render_terminal.py`는 ANSI 색상 코드(`\033[32m` 등)를 파싱해 색상을 적용한다.
  텍스트에 ANSI 코드가 없으면 흰색으로 표시된다.
- 명령 출력이 너무 길면 자동으로 줄 바꿈된다 (`--width` 기준).
- `--width`를 늘리면 가독성이 좋아지지만 파일이 커진다. 기본값 920px 권장.
- `docker ps` 같은 넓은 출력은 `--width 1200`으로 늘리면 잘리지 않는다.
- 파이프가 있는 명령: `ssh matter "printf \"...\$ cmd1 | cmd2\n\" && cmd1 | cmd2 2>&1"`
