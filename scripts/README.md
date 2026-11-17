# scripts

표준 라이브러리만 사용하는 Python 스크립트. GitHub 접근은 `gh` CLI (PATH에 없으면 `C:\Program Files\GitHub CLI\gh.exe`).

## init_project.py

새 프로젝트의 서버 측 설정을 초기화한다. 모든 단계는 반복 실행해도 안전하다. 실패한 단계는 이유와 대안을 출력하고 다음 단계를 계속한다.

```
python scripts/init_project.py [--repo OWNER/REPO] [--project-title 제목] [--dry-run] [--protect-main]
```

1. `.github/labels.yml` 라벨을 서버와 동기화 (다른 것만 `gh label create --force`)
2. 같은 제목의 Projects(v2) 재사용 또는 생성 후 저장소에 연결
3. Status 옵션을 `Backlog, Todo, In Progress, Review, Done`으로 맞춤. 이슈가 붙어 있고 옵션이 다르면 건드리지 않고 FAIL로 보고한다.
4. `--protect-main`일 때만 main 보호 (PR 필수, 승인 0, 강제 push/삭제 금지, enforce_admins=false). 요금제/권한 문제는 UNSUPPORTED로 보고.
5. `.collab/version`에 `initialized_repo=OWNER/REPO` 기록

`--dry-run`은 서버와 파일을 바꾸지 않는다. (읽기 조회만 한다.) 종료 코드: FAIL 단계가 있으면 1.

## validate_env.py

```
python scripts/validate_env.py [--repo OWNER/REPO] [--strict] [--json]
```

항목별 `PASS`, `FAIL`, `UNKNOWN`. 확인하지 못한 항목은 UNKNOWN이며 PASS가 아니다. FAIL이 있으면 종료 코드 1, `--strict`이면 UNKNOWN도 1.

## .collab/version 형식

UTF-8(BOM 없음), LF, `key=value` 한 줄씩. `#` 시작 줄과 빈 줄은 무시. key는 소문자와 `_`.

```
version=0.1.0-dev
template=huigeun6011-prog/collab-template
```

- `version` (필수): SemVer. `template` (필수): 템플릿 저장소 `OWNER/REPO`.
- `initialized_repo` (선택): `init_project.py`가 기록하는 초기화 대상 저장소.

## 테스트

```
python -m unittest discover -s tests
```
