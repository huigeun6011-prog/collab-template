# collab-template

한 명의 인간 책임자와 여러 독립 AI 에이전트가 협업하기 위한 **재사용 가능한 프로젝트 템플릿(프로젝트 A)** 입니다.
이 저장소로 실제 업무 프로젝트(프로젝트 B)를 반복 생성합니다.

> 상태: 초기 구축 중 (Phase 1). 버전은 `.collab/version` 참고.

## 이 저장소가 하는 일

- 공통 협업 규칙, AI 에이전트 업무 규칙, Issue/PR 템플릿 제공
- GitHub 서버 측 설정(라벨, Projects, 브랜치 정책) 초기화 스크립트
- 협업 환경 검증 스크립트
- 환경 자체의 버전 관리

## 이 저장소에 없는 것

특정 업무 프로젝트의 요구사항, 소스코드, 데이터, 분석 결과, 실제 업무 이슈.

## 협업 방식

GitHub Flow + Kanban(GitHub Projects). 모든 작업은 Issue → 브랜치 → Pull Request → 리뷰 → Merge 순서로 진행합니다.
자세한 규칙은 `CONTRIBUTING.md`, `AGENTS.md`(작성 예정)를 참고하세요.

## 주요 결정 기록

`docs/adr/` 참고.
