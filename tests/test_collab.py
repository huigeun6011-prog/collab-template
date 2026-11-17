import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import collab_lib as lib  # noqa: E402
import init_project  # noqa: E402
import validate_env  # noqa: E402

LABELS = '''# comment
- name: "type:task"
  color: "1d76db"
  description: "일반 업무"
- name: "agent:dev-01"
  color: "C5DEF5"
  description: "AI-DEV-01"
'''


def ok(out=""):
    return lib.Result(0, out, "")


def fail(err="boom"):
    return lib.Result(1, "", err)


class FakeGh:
    """gh 호출을 흉내낸다. calls에 모든 호출을 기록한다."""

    def __init__(self, labels=None, projects=None, linked=True, status=None,
                 items=None, protection="none", scopes="repo, project, workflow"):
        self.labels = labels if labels is not None else []
        self.projects = projects if projects is not None else []
        self.linked = linked
        self.status = status if status is not None else ["Todo", "In Progress", "Done"]
        self.items = items or []
        self.protection = protection
        self.scopes = scopes
        self.calls = []

    def __call__(self, args, input_text=None):
        self.calls.append(list(args))
        a = args
        if a[:2] == ["label", "list"]:
            return ok(json.dumps(self.labels))
        if a[:2] == ["label", "create"]:
            return ok()
        if a[:2] == ["api", "-i"]:
            return ok("HTTP/2.0 200 OK\nX-Oauth-Scopes: %s\n\n{}" % self.scopes)
        if a[0] == "api" and "protection" in a[-1] or (a[0] == "api" and "protection" in " ".join(a)):
            if "PUT" in a:
                return ok("{}")
            if self.protection == "none":
                return fail("gh: Branch not protected (HTTP 404)")
            if self.protection == "paid":
                return fail("gh: Upgrade to GitHub Pro (HTTP 403)")
            return ok(json.dumps(self.protection))
        if a[:3] == ["api", "graphql", "--input"]:
            return ok(json.dumps({"data": {"updateProjectV2Field": {}}}))
        if a[:2] == ["api", "graphql"]:
            with open(a[3][len("query=@"):], encoding="utf-8") as f:
                q = f.read()
            return ok(json.dumps({"data": self._gql(q)}))
        return fail("unexpected: %r" % a)

    def _gql(self, q):
        if "createProjectV2" in q:
            return {"createProjectV2": {"projectV2": {"id": "P1", "number": 1, "url": "u"}}}
        if "linkProjectV2ToRepository" in q:
            return {"linkProjectV2ToRepository": {"repository": {"id": "R"}}}
        if "repositoryOwner" in q:
            return {"repositoryOwner": {"projectsV2": {"nodes": self.projects}}}
        if "repository(" in q:
            linked = self.projects if self.linked else []
            return {"repository": {"id": "R", "owner": {"id": "O", "login": "o"},
                                   "projectsV2": {"nodes": linked}}}
        if "field(name" in q:
            return {"node": {
                "field": {"id": "F", "options": [{"id": n, "name": n} for n in self.status]},
                "items": {"totalCount": len(self.items),
                          "nodes": [{"fieldValueByName": {"name": n}} for n in self.items]}}}
        raise AssertionError(q)


class TmpRoot(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        for rel, text in {".github/labels.yml": LABELS,
                          ".collab/version": "version=0.1.0-dev\ntemplate=o/t\n"}.items():
            p = os.path.join(self.root, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)


class LibTests(unittest.TestCase):
    def test_parse_labels(self):
        l = lib.parse_labels(LABELS)
        self.assertEqual([x["name"] for x in l], ["type:task", "agent:dev-01"])
        self.assertEqual(l[1]["color"], "c5def5")
        self.assertEqual(l[0]["description"], "일반 업무")

    def test_parse_labels_rejects_garbage(self):
        with self.assertRaises(ValueError):
            lib.parse_labels("not yaml at all")

    def test_real_labels_file_parses(self):
        labels = lib.load_labels()
        self.assertIn("agent:dev-01", [x["name"] for x in labels])

    def test_version_roundtrip(self):
        d = lib.parse_version("# c\nversion=0.1.0-dev\ntemplate=a/b\n")
        self.assertEqual(d, {"version": "0.1.0-dev", "template": "a/b"})
        self.assertEqual(lib.format_version(d), "version=0.1.0-dev\ntemplate=a/b\n")
        with self.assertRaises(ValueError):
            lib.parse_version("0.0.0-bootstrap")

    def test_write_version_no_bom_lf_idempotent(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        self.assertTrue(lib.write_version({"version": "1.0.0", "template": "a/b"}, root))
        self.assertFalse(lib.write_version({"version": "1.0.0", "template": "a/b"}, root))
        with open(lib.version_path(root), "rb") as f:
            raw = f.read()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", raw)

    def test_parse_remote_url(self):
        self.assertEqual(lib.parse_remote_url("https://github.com/o/r.git\n"), "o/r")
        self.assertEqual(lib.parse_remote_url("git@github.com:o/r.git"), "o/r")
        self.assertIsNone(lib.parse_remote_url("https://example.com/x"))


class ValidateTests(TmpRoot):
    def server_labels(self, color="c5def5"):
        return [{"name": "type:task", "color": "1d76db", "description": "일반 업무"},
                {"name": "agent:dev-01", "color": color, "description": "AI-DEV-01"}]

    def test_label_pass_fail_unknown(self):
        gh = FakeGh(labels=self.server_labels())
        self.assertEqual(validate_env.check_labels(gh, "o/r", self.root)["status"], "PASS")
        gh = FakeGh(labels=self.server_labels(color="000000"))
        self.assertEqual(validate_env.check_labels(gh, "o/r", self.root)["status"], "FAIL")
        gh = FakeGh(labels=self.server_labels()[:1])
        self.assertEqual(validate_env.check_labels(gh, "o/r", self.root)["status"], "FAIL")
        self.assertEqual(validate_env.check_labels(lambda a, i=None: fail("net"), "o/r",
                                                   self.root)["status"], "UNKNOWN")

    def test_status_options(self):
        proj = [{"id": "P1", "title": "r", "number": 1}]
        gh = FakeGh(projects=proj, status=lib.STATUS_OPTIONS)
        self.assertEqual([c["status"] for c in validate_env.check_project(gh, "o/r", "r")],
                         ["PASS", "PASS"])
        gh = FakeGh(projects=proj, status=["Todo"])
        self.assertEqual([c["status"] for c in validate_env.check_project(gh, "o/r", "r")],
                         ["PASS", "FAIL"])
        gh = FakeGh(projects=[])
        self.assertEqual([c["status"] for c in validate_env.check_project(gh, "o/r", "r")],
                         ["FAIL", "UNKNOWN"])
        self.assertEqual([c["status"] for c in validate_env.check_project(
            lambda a, i=None: fail("x"), "o/r", "r")], ["UNKNOWN", "UNKNOWN"])

    def test_protection(self):
        self.assertEqual(validate_env.check_protection(FakeGh(protection="none"), "o/r")["status"], "FAIL")
        self.assertEqual(validate_env.check_protection(FakeGh(protection="paid"), "o/r")["status"], "UNKNOWN")
        good = {"required_pull_request_reviews": {}, "allow_force_pushes": {"enabled": False},
                "allow_deletions": {"enabled": False}}
        self.assertEqual(validate_env.check_protection(FakeGh(protection=good), "o/r")["status"], "PASS")
        bad = dict(good, allow_force_pushes={"enabled": True})
        self.assertEqual(validate_env.check_protection(FakeGh(protection=bad), "o/r")["status"], "FAIL")

    def test_scopes(self):
        r = validate_env.check_gh_auth(FakeGh(scopes="repo, project"))
        self.assertEqual([c["status"] for c in r], ["PASS", "FAIL"])
        r = validate_env.check_gh_auth(lambda a, i=None: lib.Result(127, "", "no gh"))
        self.assertEqual([c["status"] for c in r], ["UNKNOWN"])

    def test_files_and_version(self):
        res = validate_env.check_files(self.root)
        self.assertTrue(any(r["status"] == "FAIL" for r in res))  # README 등 없음
        self.assertEqual(validate_env.check_version(self.root)["status"], "PASS")
        lib.write_version({"version": "bad", "template": "x"}, self.root)
        self.assertEqual(validate_env.check_version(self.root)["status"], "FAIL")

    def test_exit_code(self):
        p, f, u = ({"status": s} for s in ("PASS", "FAIL", "UNKNOWN"))
        self.assertEqual(validate_env.exit_code([p, u]), 0)
        self.assertEqual(validate_env.exit_code([p, u], strict=True), 1)
        self.assertEqual(validate_env.exit_code([p, f]), 1)


class InitTests(TmpRoot):
    def make(self, read, write, **kw):
        out = []
        return init_project.Initializer("o/r", "r", read, write, root=self.root,
                                        out=out.append, **kw), out

    def test_dry_run_never_writes(self):
        server = FakeGh()  # 라벨, 프로젝트 모두 없음
        writes = FakeGh()
        init, _ = self.make(server, writes, dry_run=True, protect_main=True)
        self.assertEqual(init.run(), 0)
        self.assertEqual(writes.calls, [])
        self.assertTrue(any(s.status == "PLAN" for s in init.steps))
        self.assertEqual(lib.read_version(self.root), {"version": "0.1.0-dev", "template": "o/t"})

    def test_creates_then_second_run_is_noop(self):
        labels = [{"name": "type:task", "color": "1d76db", "description": "일반 업무"},
                  {"name": "agent:dev-01", "color": "c5def5", "description": "AI-DEV-01"}]
        proj = [{"id": "P1", "title": "r", "number": 1}]
        # 첫 실행: 라벨 없음, 프로젝트 없음
        server, writes = FakeGh(), FakeGh()
        init, _ = self.make(server, writes)
        self.assertEqual(init.run(), 0)
        w = [c for c in writes.calls]
        self.assertEqual(len([c for c in w if c[:2] == ["label", "create"]]), 2)
        self.assertTrue(any(c[:3] == ["api", "graphql", "--input"] for c in w))
        # 두 번째 실행: 서버가 이미 구성됨
        server, writes = FakeGh(labels=labels, projects=proj, status=lib.STATUS_OPTIONS), FakeGh()
        init, _ = self.make(server, writes)
        self.assertEqual(init.run(), 0)
        self.assertEqual(writes.calls, [])
        self.assertEqual([s.status for s in init.steps],
                         ["SKIP", "SKIP", "SKIP", "SKIP", "SKIP"])

    def test_status_with_attached_items_not_touched(self):
        proj = [{"id": "P1", "title": "r", "number": 1}]
        server = FakeGh(labels=[], projects=proj, status=["Todo", "Done"], items=["Todo"])
        writes = FakeGh()
        init, _ = self.make(server, writes)
        init.run()
        st = [s for s in init.steps if s.name == "Project Status 옵션"][0]
        self.assertEqual(st.status, "FAIL")
        self.assertFalse(any(c[:3] == ["api", "graphql", "--input"] for c in writes.calls))

    def test_no_protection_without_flag(self):
        writes = FakeGh()
        init, _ = self.make(FakeGh(), writes)
        init.run()
        self.assertFalse(any("protection" in " ".join(c) for c in writes.calls))

    def test_failed_step_does_not_stop_others(self):
        def bad_read(args, input_text=None):
            return fail("HTTP 500")
        init, _ = self.make(bad_read, FakeGh())
        self.assertEqual(init.run(), 1)
        self.assertEqual(len(init.steps), 5)

    def test_protection_unsupported_reported(self):
        class Paid(FakeGh):
            def __call__(self, args, input_text=None):
                if "PUT" in args:
                    return fail("gh: Upgrade to GitHub Pro or make this repository public (HTTP 403)")
                return super().__call__(args, input_text)
        init, _ = self.make(FakeGh(), Paid(), protect_main=True)
        init.run()
        st = [s for s in init.steps if s.name == "main 브랜치 보호"][0]
        self.assertEqual(st.status, "UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
