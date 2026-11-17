# Kanban 운영 규칙

GitHub Projects의 `Status` 필드로 관리합니다. 별도의 작업 목록 파일은 두지 않습니다.

## 상태

| 상태 | 의미 | 진입 조건 |
|---|---|---|
| Backlog | 아직 착수 전 | Issue 등록 |
| Todo | 착수 준비 완료 | 완료 조건이 명확하고 담당자 지정 |
| In Progress | 진행 중 | 브랜치 생성 |
| Review | 리뷰 대기 | PR 제출 |
| Done | 완료 | PR Merge, Issue 종료 |

## Blocked

별도 상태 대신 `status:blocked` 라벨을 쓴다. Issue 본문이나 댓글에 **무엇 때문에 막혔는지**(Issue 번호 또는 결정 필요 사항)를 적는다.
막힘이 풀리면 라벨을 제거한다.

## 우선순위

`priority:high`, `priority:medium`, `priority:low` 라벨. 라벨이 없으면 medium으로 본다.

## WIP 제한

GitHub Projects는 WIP 제한을 강제하지 못하므로 규칙으로 관리한다.

- **In Progress**: 에이전트 1명당 최대 1개
- **Review**: 최대 3개. 넘으면 새 작업보다 리뷰를 먼저 처리한다.

## 의존성

Issue 본문에 `Depends on #N`을 적는다. 의존 대상이 닫히기 전에는 `Todo`로 올리지 않는다.

## 담당자

Issue 본문의 `Agent:` 줄과 라벨(`agent:<role>-<nn>`, [규칙](AGENT-IDENTITY.md))로 표시한다. 단일 GitHub 계정 사용 중이므로 Assignees 필드는 에이전트를 구분하지 못한다.

## 완료 조건

Issue 본문에 체크리스트로 쓴다. PR이 모든 항목을 만족해야 Merge한다.
