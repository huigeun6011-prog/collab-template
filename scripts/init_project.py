#!/usr/bin/env python3
"""새 프로젝트의 GitHub 서버 측 설정(라벨, Projects, 브랜치 보호)을 초기화한다.

모든 단계는 반복 실행해도 안전하다. --dry-run은 서버를 바꾸지 않고 할 일만 출력한다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collab_lib as lib  # noqa: E402

M_CREATE_PROJECT = """mutation($owner:ID!,$title:String!){
  createProjectV2(input:{ownerId:$owner,title:$title}){projectV2{id number url}}
}"""
M_LINK = """mutation($project:ID!,$repo:ID!){
  linkProjectV2ToRepository(input:{projectId:$project,repositoryId:$repo}){repository{id}}
}"""
M_STATUS = """mutation($field:ID!,$opts:[ProjectV2SingleSelectFieldOptionInput!]!){
  updateProjectV2Field(input:{fieldId:$field,singleSelectOptions:$opts}){
    projectV2Field{... on ProjectV2SingleSelectField{id}}
  }
}"""


class Step:
    # status: OK(변경함), SKIP(이미 같음), PLAN(dry-run 예정), FAIL, UNSUPPORTED
    def __init__(self, name, status, detail=""):
        self.name, self.status, self.detail = name, status, detail


PLAN_LIMIT_PHRASES = ("upgrade to github pro", "make this repository public")


def _is_unsupported(err):
    """요금제 제한을 가리키는 GitHub 메시지만 지원 안 됨으로 본다. 그 외 403/404는 FAIL."""
    e = err.lower()
    return any(p in e for p in PLAN_LIMIT_PHRASES)


class Initializer:
    def __init__(self, repo, title, read, write, dry_run=False, protect_main=False,
                 root=lib.REPO_ROOT, out=print):
        self.repo, self.title = repo, title
        self.read, self.write = read, write
        self.dry_run, self.protect_main = dry_run, protect_main
        self.root, self.out = root, out
        self.steps = []
        self.repo_info = None
        self.project = None

    def add(self, step):
        self.steps.append(step)
        extra = (": " + step.detail) if step.detail else ""
        self.out("[%s] %s%s" % (step.status, step.name, extra))

    # 1. 라벨
    def labels(self):
        name = "라벨 동기화"
        try:
            desired = lib.load_labels(self.root)
        except (OSError, ValueError) as e:
            return self.add(Step(name, "FAIL", "labels.yml을 읽을 수 없음: %s" % e))
        r = self.read(["label", "list", "-R", self.repo, "--limit", "500",
                       "--json", "name,color,description"])
        if r.rc != 0:
            return self.add(Step(name, "FAIL", "서버 라벨 조회 실패: %s 대안: gh auth status 확인"
                                 % r.err.strip()))
        server = {l["name"]: l for l in json.loads(r.out)}
        changed, failed, planned = 0, [], 0
        for lb in desired:
            cur = server.get(lb["name"])
            if cur and cur["color"].lower() == lb["color"] and (cur["description"] or "") == lb["description"]:
                continue
            if self.dry_run:
                planned += 1
                self.out("  (dry-run) 라벨 %s: %s" % ("갱신" if cur else "생성", lb["name"]))
                continue
            w = self.write(["label", "create", lb["name"], "-R", self.repo, "--force",
                            "--color", lb["color"], "--description", lb["description"]])
            if w.rc == 0:
                changed += 1
            else:
                failed.append("%s (%s)" % (lb["name"], w.err.strip()))
        if failed:
            return self.add(Step(name, "FAIL", "실패: " + "; ".join(failed)))
        if planned:
            return self.add(Step(name, "PLAN", "%d개 생성/갱신 예정" % planned))
        if changed:
            return self.add(Step(name, "OK", "%d개 생성/갱신" % changed))
        self.add(Step(name, "SKIP", "서버 라벨이 이미 labels.yml과 같음 (%d개)" % len(desired)))

    # 2. Project
    def project_step(self):
        name = "Projects 생성/연결"
        info, err = lib.get_repo_info(self.read, self.repo)
        if not info:
            return self.add(Step(name, "FAIL", "저장소 조회 실패: %s 대안: --repo 확인, project 스코프 확인 "
                                 "(gh auth refresh -s project)" % err))
        self.repo_info = info
        proj, err = lib.find_project(self.read, info, self.title)
        if err:
            return self.add(Step(name, "FAIL", err + " 대안: gh auth refresh -s project"))
        created = False
        if proj is None:
            if self.dry_run:
                self.add(Step(name, "PLAN", "'%s' 프로젝트를 생성하고 저장소에 연결 예정" % self.title))
                return
            r, data = lib.graphql(self.write, M_CREATE_PROJECT, owner=info["owner"]["id"],
                                  title=self.title)
            if data is None:
                return self.add(Step(name, "FAIL", "프로젝트 생성 실패: %s" % r.err.strip()))
            proj = data["createProjectV2"]["projectV2"]
            created = True
        self.project = proj
        linked = any(n and n["id"] == proj["id"] for n in (info.get("projectsV2") or {}).get("nodes") or [])
        if linked:
            return self.add(Step(name, "OK" if created else "SKIP",
                                 "프로젝트 #%s 생성됨, 이미 연결됨" % proj.get("number") if created
                                 else "프로젝트 #%s 재사용, 이미 연결됨" % proj.get("number")))
        if self.dry_run:
            return self.add(Step(name, "PLAN", "프로젝트 #%s를 저장소에 연결 예정" % proj.get("number")))
        r, data = lib.graphql(self.write, M_LINK, project=proj["id"], repo=info["id"])
        if data is None:
            return self.add(Step(name, "FAIL", "저장소 연결 실패: %s" % r.err.strip()))
        self.add(Step(name, "OK", "프로젝트 #%s %s, 저장소에 연결" %
                      (proj.get("number"), "생성" if created else "재사용")))

    # 3. Status 옵션
    def status_step(self):
        name = "Project Status 옵션"
        if self.project is None:
            if self.dry_run:
                return self.add(Step(name, "PLAN", "프로젝트 생성 후 Status를 %s로 맞출 예정"
                                     % ", ".join(lib.STATUS_OPTIONS)))
            return self.add(Step(name, "FAIL", "프로젝트가 없어 건너뜀 (앞 단계 실패)"))
        field, items, err = lib.get_status_field(self.read, self.project["id"])
        if field is None:
            return self.add(Step(name, "FAIL", err))
        cur = [o["name"] for o in field["options"]]
        want = lib.STATUS_OPTIONS
        if cur == want:
            return self.add(Step(name, "SKIP", "이미 같음: " + ", ".join(cur)))
        if items.get("truncated"):
            return self.add(Step(name, "FAIL",
                "프로젝트 항목이 %d개로 조회 한도(100)를 넘어 Status 사용 여부를 전부 확인할 수 없어 "
                "옵션을 바꾸지 않음. 대안: GitHub UI에서 직접 맞추거나 항목을 정리한 뒤 재실행"
                % items["total"]))
        if items["total"] and items["used_options"]:
            # 옵션을 교체하면 옵션 ID가 바뀌어 붙어 있는 이슈의 Status가 지워질 수 있다. (추정)
            return self.add(Step(name, "FAIL",
                "이슈가 이미 붙어 있어 옵션을 바꾸지 않음 (현재: %s, 사용 중: %s). "
                "대안: GitHub UI에서 직접 맞추거나 항목을 정리한 뒤 재실행"
                % (", ".join(cur), ", ".join(items["used_options"]))))
        if self.dry_run:
            return self.add(Step(name, "PLAN", "%s -> %s" % (", ".join(cur), ", ".join(want))))
        opts = json.dumps([{"name": n, "color": lib.STATUS_COLORS[n], "description": ""}
                           for n in want])
        r, data = self._status_mutation(field["id"], opts)
        if data is None:
            return self.add(Step(name, "FAIL", "Status 갱신 실패: %s" % r.err.strip()))
        self.add(Step(name, "OK", "%s -> %s" % (", ".join(cur), ", ".join(want))))

    def _status_mutation(self, field_id, opts_json):
        # 배열 변수는 -f 문자열로 못 넘기므로 JSON 본문으로 전달한다.
        body = json.dumps({"query": M_STATUS,
                           "variables": {"field": field_id, "opts": json.loads(opts_json)}})
        r = self.write(["api", "graphql", "--input", "-"], body)
        if r.rc != 0:
            return r, None
        try:
            resp = json.loads(r.out)
        except ValueError:
            return lib.Result(1, r.out, "응답이 JSON이 아님"), None
        if resp.get("errors"):
            return lib.Result(1, r.out, "; ".join(e.get("message", "?") for e in resp["errors"])), None
        return r, resp.get("data")

    # 4. 브랜치 보호
    def protect_step(self):
        name = "main 브랜치 보호"
        if not self.protect_main:
            return self.add(Step(name, "SKIP", "--protect-main 없음: 브랜치 보호를 바꾸지 않음"))
        if self.dry_run:
            return self.add(Step(name, "PLAN", "PR 필수, 승인 0, 강제 push/삭제 금지, enforce_admins=false 적용 예정"))
        body = json.dumps({
            "required_status_checks": None,
            "enforce_admins": False,
            "required_pull_request_reviews": {"required_approving_review_count": 0},
            "restrictions": None,
            "allow_force_pushes": False,
            "allow_deletions": False,
        })
        r = self.write(["api", "-X", "PUT", "repos/%s/branches/main/protection" % self.repo,
                        "--input", "-"], body)
        if r.rc == 0:
            return self.add(Step(name, "OK", "적용함"))
        if _is_unsupported(r.err + r.out):
            return self.add(Step(name, "UNSUPPORTED",
                "지원 안 됨 (요금제 제한): %s 대안: 유료 플랜 사용 또는 공개 저장소 전환. "
                "공개 범위 변경과 유료 서비스 도입은 사람 승인 필요 (이 스크립트는 하지 않음)" % r.err.strip()))
        self.add(Step(name, "FAIL", r.err.strip()))

    # 5. 버전 파일
    def version_step(self):
        name = ".collab/version 갱신"
        try:
            data = lib.read_version(self.root)
        except (OSError, ValueError) as e:
            return self.add(Step(name, "FAIL", "읽을 수 없음: %s" % e))
        data["initialized_repo"] = self.repo
        if self.dry_run:
            return self.add(Step(name, "PLAN", "initialized_repo=%s 기록 예정" % self.repo))
        try:
            changed = lib.write_version(data, self.root)
        except OSError as e:
            return self.add(Step(name, "FAIL", str(e)))
        self.add(Step(name, "OK" if changed else "SKIP",
                      "initialized_repo=%s" % self.repo if changed else "이미 같음"))

    def run(self):
        self.out("대상: %s%s" % (self.repo, "  (dry-run: 서버를 바꾸지 않음)" if self.dry_run else ""))
        for fn in (self.labels, self.project_step, self.status_step,
                   self.protect_step, self.version_step):
            try:
                fn()
            except Exception as e:  # 한 단계의 예외가 다른 단계를 막지 않게 한다.
                self.add(Step(fn.__name__, "FAIL", "예외: %r" % e))
        return 1 if any(s.status == "FAIL" for s in self.steps) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", help="OWNER/REPO (기본: origin 원격에서 추정)")
    ap.add_argument("--project-title", help="Projects 제목 (기본: 저장소 이름)")
    ap.add_argument("--dry-run", action="store_true", help="서버를 바꾸지 않고 할 일만 출력")
    ap.add_argument("--protect-main", action="store_true", help="main 브랜치 보호 적용 (기본 꺼짐)")
    ap.add_argument("--root", default=lib.REPO_ROOT, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    repo = a.repo or lib.detect_repo(a.root)
    if not repo:
        print("저장소를 알 수 없음: --repo OWNER/REPO를 지정하세요.", file=sys.stderr)
        return 2
    try:
        lib.split_repo(repo)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    title = a.project_title or repo.split("/")[1]
    init = Initializer(repo, title, lib.run_gh, lib.run_gh, a.dry_run, a.protect_main, a.root)
    return init.run()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
