#!/usr/bin/env python3
"""협업 환경 검증. 항목별로 PASS / FAIL / UNKNOWN을 구분한다.

확인하지 못한 항목은 UNKNOWN이며 PASS로 처리하지 않는다.
종료 코드: FAIL이 있으면 1, 없으면 0. --strict이면 UNKNOWN도 1.
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collab_lib as lib  # noqa: E402

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
REQUIRED_FILES = ["README.md", "AGENTS.md", "CONTRIBUTING.md",
                  ".github/PULL_REQUEST_TEMPLATE.md", ".github/labels.yml",
                  ".collab/version"]
REQUIRED_SCOPES = ["repo", "project", "workflow"]
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")


def check(name, status, detail=""):
    return {"name": name, "status": status, "detail": detail}


def check_files(root):
    out = []
    for rel in REQUIRED_FILES:
        ok = os.path.isfile(os.path.join(root, *rel.split("/")))
        out.append(check("파일 " + rel, PASS if ok else FAIL, "" if ok else "없음"))
    n = len(glob.glob(os.path.join(root, ".github", "ISSUE_TEMPLATE", "*")))
    out.append(check("파일 .github/ISSUE_TEMPLATE/*", PASS if n else FAIL,
                     "%d개" % n if n else "없음"))
    ok = os.path.isdir(os.path.join(root, "docs", "adr"))
    out.append(check("디렉터리 docs/adr/", PASS if ok else FAIL, "" if ok else "없음"))
    return out


def check_version(root):
    name = ".collab/version 형식"
    try:
        data = lib.read_version(root)
    except OSError as e:
        return check(name, FAIL, "읽을 수 없음: %s" % e)
    except ValueError as e:
        return check(name, FAIL, str(e))
    v = data.get("version")
    if not v or not SEMVER.match(v):
        return check(name, FAIL, "version 값이 없거나 형식이 틀림: %r" % v)
    if not data.get("template"):
        return check(name, FAIL, "template 값이 없음")
    return check(name, PASS, "version=%s" % v)


def check_gh_auth(gh):
    r = gh(["api", "-i", "user"])
    if r.rc == 127:
        return [check("gh 인증", UNKNOWN, r.err.strip())]
    if r.rc != 0:
        msg = r.err.strip().splitlines()[0] if r.err.strip() else "실패"
        low = (r.err + r.out).lower()
        if any(h in low for h in ("gh auth login", "not logged in", "http 401", "bad credentials")):
            return [check("gh 인증", FAIL, "인증되지 않음 (gh auth login 필요): %s" % msg)]
        return [check("gh 인증", UNKNOWN, "확인하지 못함 (네트워크 오류 등): %s" % msg)]
    out = [check("gh 인증", PASS)]
    m = re.search(r"^x-oauth-scopes:\s*(.*)$", r.out, re.I | re.M)
    if not m:
        out.append(check("gh 스코프", UNKNOWN, "응답에 스코프 헤더가 없음 (fine-grained 토큰 등)"))
        return out
    have = {s.strip() for s in m.group(1).split(",") if s.strip()}
    missing = [s for s in REQUIRED_SCOPES if s not in have]
    out.append(check("gh 스코프 (repo, project, workflow)", FAIL if missing else PASS,
                     ("부족: %s (gh auth refresh -s %s)" % (", ".join(missing), ",".join(missing)))
                     if missing else ""))
    return out


def check_labels(gh, repo, root):
    name = "서버 라벨 == labels.yml"
    try:
        desired = lib.load_labels(root)
    except (OSError, ValueError) as e:
        return check(name, FAIL, "labels.yml 오류: %s" % e)
    r = gh(["label", "list", "-R", repo, "--limit", "500", "--json", "name,color,description"])
    if r.rc != 0:
        return check(name, UNKNOWN, "서버 라벨을 조회하지 못함: %s" % r.err.strip())
    try:
        server = {l["name"]: l for l in json.loads(r.out)}
    except ValueError:
        return check(name, UNKNOWN, "라벨 응답을 해석하지 못함")
    problems = []
    for lb in desired:
        s = server.get(lb["name"])
        if s is None:
            problems.append("없음: %s" % lb["name"])
            continue
        if s["color"].lower() != lb["color"]:
            problems.append("색 불일치: %s (서버 %s, 파일 %s)" % (lb["name"], s["color"], lb["color"]))
        if (s.get("description") or "") != lb["description"]:
            problems.append("설명 불일치: %s" % lb["name"])
    if problems:
        return check(name, FAIL, "; ".join(problems))
    return check(name, PASS, "%d개 일치" % len(desired))


def check_project(gh, repo, title):
    n1, n2 = "Projects 연결", "Projects Status 옵션"
    try:
        info, err = lib.get_repo_info(gh, repo)
    except ValueError as e:
        return [check(n1, UNKNOWN, str(e)), check(n2, UNKNOWN, str(e))]
    if not info:
        msg = "조회하지 못함: %s (project 스코프 확인)" % err
        return [check(n1, UNKNOWN, msg), check(n2, UNKNOWN, msg)]
    nodes = [n for n in (info.get("projectsV2") or {}).get("nodes") or [] if n]
    if not nodes:
        return [check(n1, FAIL, "저장소에 연결된 프로젝트가 없음"),
                check(n2, UNKNOWN, "연결된 프로젝트가 없어 확인하지 못함")]
    proj = next((n for n in nodes if n["title"] == title), None)
    if proj is None:
        return [check(n1, FAIL, "제목 '%s' 프로젝트가 연결돼 있지 않음 (연결됨: %s)"
                      % (title, ", ".join(n["title"] for n in nodes))),
                check(n2, UNKNOWN, "대상 프로젝트가 없어 확인하지 못함")]
    out = [check(n1, PASS, "'%s' (#%s)" % (proj["title"], proj["number"]))]
    field, _items, err = lib.get_status_field(gh, proj["id"])
    if field is None:
        out.append(check(n2, UNKNOWN, err))
    else:
        cur = [o["name"] for o in field["options"]]
        if cur == lib.STATUS_OPTIONS:
            out.append(check(n2, PASS, ", ".join(cur)))
        else:
            out.append(check(n2, FAIL, "현재: %s / 기대: %s" % (", ".join(cur),
                                                           ", ".join(lib.STATUS_OPTIONS))))
    return out


def check_protection(gh, repo):
    name = "main 브랜치 보호"
    r = gh(["api", "repos/%s/branches/main/protection" % repo])
    if r.rc != 0:
        e = (r.err + r.out).lower()
        if "branch not protected" in e:
            return check(name, FAIL, "main이 보호되지 않음 (init_project.py --protect-main)")
        if "upgrade to github pro" in e or "http 403" in e:
            return check(name, UNKNOWN, "요금제 미지원 또는 권한 없음으로 확인하지 못함")
        return check(name, UNKNOWN, "조회하지 못함: %s" % r.err.strip())
    try:
        p = json.loads(r.out)
    except ValueError:
        return check(name, UNKNOWN, "응답을 해석하지 못함")
    problems = []
    if "required_pull_request_reviews" not in p:
        problems.append("PR 필수 아님")
    if (p.get("allow_force_pushes") or {}).get("enabled"):
        problems.append("강제 push 허용")
    if (p.get("allow_deletions") or {}).get("enabled"):
        problems.append("삭제 허용")
    return check(name, FAIL if problems else PASS, ", ".join(problems))


def check_worktree(root):
    r = lib.run_git(["worktree", "list"], cwd=root)
    if r.rc == 127:
        return check("git worktree", UNKNOWN, r.err.strip())
    if r.rc != 0:
        return check("git worktree", FAIL, r.err.strip() or "git worktree list 실패")
    return check("git worktree", PASS, "사용 가능")


def run_checks(gh, root, repo, title):
    results = check_files(root)
    results.append(check_version(root))
    results += check_gh_auth(gh)
    if repo:
        results.append(check_labels(gh, repo, root))
        results += check_project(gh, repo, title)
        results.append(check_protection(gh, repo))
    else:
        for n in ("서버 라벨 == labels.yml", "Projects 연결", "Projects Status 옵션", "main 브랜치 보호"):
            results.append(check(n, UNKNOWN, "저장소를 알 수 없음 (--repo 지정)"))
    results.append(check_worktree(root))
    return results


def exit_code(results, strict=False):
    if any(r["status"] == FAIL for r in results):
        return 1
    if strict and any(r["status"] == UNKNOWN for r in results):
        return 1
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", help="OWNER/REPO (기본: origin 원격에서 추정)")
    ap.add_argument("--project-title", help="Projects 제목 (기본: 저장소 이름)")
    ap.add_argument("--strict", action="store_true", help="UNKNOWN도 실패로 처리")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    ap.add_argument("--root", default=lib.REPO_ROOT, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    repo = a.repo or lib.detect_repo(a.root)
    title = a.project_title or (repo.split("/")[1] if repo and "/" in repo else "")
    results = run_checks(lib.run_gh, a.root, repo, title)
    code = exit_code(results, a.strict)
    if a.json:
        print(json.dumps({"repo": repo, "results": results, "exit_code": code},
                         ensure_ascii=False, indent=2))
    else:
        print("대상: %s" % (repo or "알 수 없음"))
        for r in results:
            print("[%s] %s%s" % (r["status"], r["name"], (": " + r["detail"]) if r["detail"] else ""))
        c = {s: sum(1 for r in results if r["status"] == s) for s in (PASS, FAIL, UNKNOWN)}
        print("요약: PASS %d, FAIL %d, UNKNOWN %d" % (c[PASS], c[FAIL], c[UNKNOWN]))
    return code


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
