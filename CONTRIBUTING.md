# CONTRIBUTING — 협업 절차

사람과 AI 모두 같은 절차를 따릅니다. AI 전용 규칙은 [AGENTS.md](AGENTS.md)를 참고하세요.

## 기본 방식

GitHub Flow + Kanban(GitHub Projects). `main`은 항상 배포 가능한 상태를 유지합니다.

## 표준 절차

1. **Issue 등록**: 목적, 완료 조건 포함. 템플릿 사용.
2. **담당 지정**: 담당 에이전트(또는 사람)의 식별자를 Issue에 적는다. Projects 상태를 `Todo`로.
3. **브랜치와 작업 공간 생성**: 아래 "작업 공간" 참고.
4. **작업**: 상태를 `In Progress`로.
5. **자체 검증**: 실제로 실행한 것만 기록한다.
6. **Commit**: 작은 단위로. 메시지에 `Agent:` trailer.
7. **PR 제출**: 템플릿 사용. 상태를 `Review`로.
8. **독립 리뷰**: 작성자와 다른 식별자가 리뷰한다.
9. **Merge**: 아래 "Merge 정책".
10. **Issue 종료**: PR 본문에 `Closes #번호`. 상태가 `Done`이 된다.
11. **후속 업무 등록**: 남은 일은 새 Issue로.

## 브랜치 이름

`<type>/<이슈번호>-<짧은-설명>` 예: `docs/1-agents-md`, `feat/6-init-script`

type: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`

## 작업 공간 (병렬 작업)

한 디렉터리에서 브랜치를 전환하지 않는다. 작업마다 별도 worktree를 쓴다.

```
git worktree add ../<저장소>-wt/issue-<번호> -b <브랜치> main
git worktree remove ../<저장소>-wt/issue-<번호>   # 작업 종료 후
```

다른 에이전트의 worktree 안에서 작업하거나 파일을 바꾸지 않는다.

## 커밋 메시지

`<type>: <요약>` 한 줄, 빈 줄, 본문(선택), 그리고 trailer.

```
docs: AGENTS.md 추가

Agent: AI-DOC-01
```

## PR 요건

- 관련 Issue (`Closes #N`)
- 변경 목적, 변경사항
- 검증 결과 (실제 수행한 것만)
- 알려진 한계
- `Agent:` 줄

## 리뷰 정책

- 작성자와 **다른 식별자**의 에이전트 또는 사람이 리뷰한다.
- 결과를 PR 댓글로 남기고 `통과` 또는 `수정 필요`를 명시한다.
- 같은 GitHub 계정을 공유하는 동안 GitHub의 공식 Approve는 쓸 수 없다. 에이전트 리뷰는 **AI 독립 검토 기록**이다. 이를 정식 승인처럼 꾸미지 않는다.

## Merge 정책

[ADR-0002](docs/adr/0002-agent-review-and-merge-delegation.md)를 따른다. 요약:

- 독립 리뷰가 `통과`이고 검증 결과에 문제가 없으면 에이전트가 Merge할 수 있다.
- 다음은 사람의 승인이 먼저 필요하다: 저장소 공개 범위 변경, 삭제, 강제 push, 중요 데이터 삭제, 권한 확대, 유료 서비스, 브랜치 보호 변경, 버전 태그 릴리스.
- Merge 방식은 squash를 기본으로 한다.

## Kanban

상태, WIP 제한, Blocked 처리는 [docs/KANBAN.md](docs/KANBAN.md).

## 공식 정보 위치

| 정보 | 위치 |
|---|---|
| 소개 | README |
| 협업 절차 | CONTRIBUTING |
| AI 규칙 | AGENTS |
| 업무, 미해결 문제 | Issues |
| 진행 상태 | Projects |
| 변경 이력 | Commit |
| 변경 목적, 리뷰 | Pull Requests |
| 주요 결정 | `docs/adr/` |
