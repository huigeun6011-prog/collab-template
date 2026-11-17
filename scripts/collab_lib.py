"""collab-template 공용 함수. Python 표준 라이브러리만 사용한다.

gh 호출은 `runner(args, input_text=None) -> Result` 형태의 함수로 주입한다.
테스트에서는 가짜 runner로 바꿀 수 있다.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import namedtuple

Result = namedtuple("Result", "rc out err")

GH_FALLBACK = r"C:\Program Files\GitHub CLI\gh.exe"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_OPTIONS = ["Backlog", "Todo", "In Progress", "Review", "Done"]
STATUS_COLORS = {"Backlog": "GRAY", "Todo": "BLUE", "In Progress": "YELLOW",
                 "Review": "ORANGE", "Done": "GREEN"}


def find_gh():
    path = shutil.which("gh")
    if path:
        return path
    if os.path.exists(GH_FALLBACK):
        return GH_FALLBACK
    return None


def _run(cmd, input_text=None):
    try:
        p = subprocess.run(cmd, input=input_text, capture_output=True,
                           encoding="utf-8", errors="replace")
    except OSError as e:
        return Result(127, "", "실행 실패: %s" % e)
    return Result(p.returncode, p.stdout or "", p.stderr or "")


def run_gh(args, input_text=None):
    gh = find_gh()
    if gh is None:
        return Result(127, "", "gh CLI를 찾을 수 없음 (PATH 또는 %s)" % GH_FALLBACK)
    return _run([gh] + list(args), input_text)


def run_git(args, cwd=None):
    git = shutil.which("git")
    if git is None:
        return Result(127, "", "git을 찾을 수 없음")
    cmd = [git] + list(args)
    if cwd:
        cmd = [git, "-C", cwd] + list(args)
    return _run(cmd)


# ---------- labels.yml ----------

def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        q, v = v[0], v[1:-1]
        if q == '"':
            v = v.replace('\\"', '"').replace("\\\\", "\\")
        return v
    return v


def parse_labels(text):
    """labels.yml(리스트의 name/color/description 맵)을 파싱한다. 다른 구조는 ValueError."""
    labels, cur = [], None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^-\s+(\w+):\s*(.*)$", line)
        if m:
            cur = {}
            labels.append(cur)
            cur[m.group(1)] = _unquote(m.group(2))
            continue
        m = re.match(r"^\s+(\w+):\s*(.*)$", line)
        if m and cur is not None:
            cur[m.group(1)] = _unquote(m.group(2))
            continue
        raise ValueError("labels.yml %d행을 해석할 수 없음: %r" % (n, raw))
    for lb in labels:
        if "name" not in lb or not lb["name"]:
            raise ValueError("name이 없는 라벨 항목: %r" % lb)
        lb["color"] = lb.get("color", "ededed").lstrip("#").lower()
        lb["description"] = lb.get("description", "")
    return labels


def load_labels(root=REPO_ROOT):
    with open(os.path.join(root, ".github", "labels.yml"), encoding="utf-8") as f:
        return parse_labels(f.read())


# ---------- .collab/version ----------

def version_path(root=REPO_ROOT):
    return os.path.join(root, ".collab", "version")


def parse_version(text):
    """key=value 줄을 dict로. 빈 줄과 # 주석은 무시. 형식이 틀리면 ValueError."""
    data = {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("%d행: key=value 형식이 아님: %r" % (n, raw))
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if not re.match(r"^[a-z_]+$", k) or not v:
            raise ValueError("%d행: 잘못된 key 또는 빈 값: %r" % (n, raw))
        data[k] = v
    return data


def read_version(root=REPO_ROOT):
    with open(version_path(root), encoding="utf-8") as f:
        return parse_version(f.read())


def format_version(data):
    order = ["version", "template"]
    keys = [k for k in order if k in data] + sorted(k for k in data if k not in order)
    return "".join("%s=%s\n" % (k, data[k]) for k in keys)


def write_version(data, root=REPO_ROOT):
    """UTF-8(BOM 없음), LF로 쓴다. 내용이 같으면 파일을 건드리지 않고 False를 반환."""
    new = format_version(data)
    p = version_path(root)
    if os.path.exists(p):
        with open(p, encoding="utf-8", newline="") as f:
            if f.read() == new:
                return False
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    return True


# ---------- git / repo ----------

def parse_remote_url(url):
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url.strip())
    return "%s/%s" % (m.group(1), m.group(2)) if m else None


def detect_repo(root=REPO_ROOT):
    r = run_git(["remote", "get-url", "origin"], cwd=root)
    if r.rc != 0:
        return None
    return parse_remote_url(r.out)


# ---------- GraphQL ----------

def graphql(runner, query, **variables):
    """쿼리를 BOM 없는 UTF-8 임시 파일로 넘긴다. (-F query=@파일) 반환: (Result, data|None)"""
    fd, path = tempfile.mkstemp(suffix=".graphql")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(query)
        args = ["api", "graphql", "-F", "query=@" + path]
        for k, v in variables.items():
            args += ["-f", "%s=%s" % (k, v)]
        r = runner(args)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if r.rc != 0:
        return r, None
    try:
        body = json.loads(r.out)
    except ValueError:
        return Result(1, r.out, "GraphQL 응답이 JSON이 아님"), None
    if body.get("errors"):
        msg = "; ".join(e.get("message", "?") for e in body["errors"])
        return Result(1, r.out, msg), None
    return r, body.get("data")


Q_REPO = """query($owner:String!,$name:String!){
  repository(owner:$owner,name:$name){
    id
    owner{id login}
    projectsV2(first:50){nodes{id title number}}
  }
}"""

Q_OWNER_PROJECTS = """query($login:String!){
  repositoryOwner(login:$login){
    ... on ProjectV2Owner{projectsV2(first:100){nodes{id title number}}}
  }
}"""

Q_STATUS = """query($id:ID!){
  node(id:$id){
    ... on ProjectV2{
      field(name:"Status"){
        ... on ProjectV2SingleSelectField{id options{id name color description}}
      }
      items(first:100){
        totalCount
        nodes{fieldValueByName(name:"Status"){
          ... on ProjectV2ItemFieldSingleSelectValue{name}}}
      }
    }
  }
}"""


def split_repo(repo):
    if not repo or repo.count("/") != 1:
        raise ValueError("--repo는 OWNER/REPO 형식이어야 함: %r" % repo)
    return repo.split("/")


def get_repo_info(runner, repo):
    """(repository 노드 | None, 오류 메시지)"""
    owner, name = split_repo(repo)
    r, data = graphql(runner, Q_REPO, owner=owner, name=name)
    if data is None or not data.get("repository"):
        return None, r.err.strip() or "저장소 조회 실패"
    return data["repository"], ""


def find_project(runner, repo_info, title):
    """같은 제목의 프로젝트 (노드 | None, 오류). 소유자의 프로젝트 전체에서 찾는다."""
    login = repo_info["owner"]["login"]
    r, data = graphql(runner, Q_OWNER_PROJECTS, login=login)
    if data is None:
        return None, r.err.strip() or "프로젝트 목록 조회 실패"
    nodes = ((data.get("repositoryOwner") or {}).get("projectsV2") or {}).get("nodes") or []
    for n in nodes:
        if n and n.get("title") == title:
            return n, ""
    return None, ""


def get_status_field(runner, project_id):
    """(field dict | None, items 정보 dict, 오류)"""
    r, data = graphql(runner, Q_STATUS, id=project_id)
    if data is None or not data.get("node"):
        return None, {}, r.err.strip() or "Status 필드 조회 실패"
    node = data["node"]
    items = node.get("items") or {}
    used = sorted({(n.get("fieldValueByName") or {}).get("name")
                   for n in items.get("nodes") or []
                   if (n.get("fieldValueByName") or {}).get("name")})
    info = {"total": items.get("totalCount", 0), "used_options": used}
    field = node.get("field")
    if not field or "options" not in field:
        return None, info, "Status 단일 선택 필드가 없음"
    return field, info, ""
