"""deploy/01 and deploy/02 under a stub `gcloud`: what they would run, and in what state.

The scripts create billable resources, so they are never run for real here. A stub `gcloud` and `bq`
put on PATH record each call and answer the few questions the scripts ask (does the database exist,
is the index there, what is the service URL). These tests cover the changes of the security review:
the BigQuery role only with a dataset (S13), the composite index behind a caller's list of briefings,
and the evaluation data that the image has to carry.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from sayitback.store.firestore_store import BRIEFINGS
from tests.fake_firestore import FakeBackedStore
from tests.helpers import run_sync

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "deploy"
BACKEND = REPO / "backend"
INDEX_NAME = "CICAgOjXh4EK"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or not DEPLOY.is_dir(), reason="needs bash and the deploy/ folder"
)

STUB = """#!/usr/bin/env bash
# Records the call, answers what the deploy scripts ask, fails only where a test asks it to.
call="${0##*/} $*"
printf '%s\\n' "$call" >> "$STUB_LOG"
case "$call" in
  "gcloud firestore indexes composite list"*) printf '%s' "${STUB_INDEX:-}" ;;
  "gcloud firestore databases describe"*"value(locationId)"*) echo asia-south1 ;;
  "gcloud run services describe"*) echo https://say-it-back-api-abc.a.run.app ;;
  "bq show"*) exit 1 ;; # the dataset does not exist yet
  "gcloud run deploy"*)
    {
      echo "DEPLOY ARGS: $*"
      (cd "$STUB_REPO/backend/eval_data" && find . -type f | sort)
    } > "$STUB_SEEN"
    cp -R "$STUB_REPO/backend/eval_data" "$STUB_UPLOADED" # what gcloud would have uploaded
    [[ -z "${STUB_FAIL_DEPLOY:-}" ]] || exit 1 ;;
esac
exit 0
"""


@pytest.fixture
def sandbox(tmp_path) -> SimpleNamespace:
    """A copy of deploy/ in a repo of its own (so a run changes nothing here), with eval data."""
    repo = tmp_path / "repo"
    shutil.copytree(DEPLOY, repo / "deploy")
    (repo / "backend" / "eval_data").mkdir(parents=True)
    (repo / "backend" / "eval_data" / ".gitkeep").write_text("")
    (repo / "backend" / ".gcloudignore").write_text(".venv/\n")
    (repo / "eval" / "testset" / "audio").mkdir(parents=True)
    (repo / "eval" / "testset" / "items.json").write_text('{"version": "v", "items": []}')
    (repo / "eval" / "testset" / "audio" / "a.wav").write_bytes(b"RIFF")
    (repo / "eval" / "reports").mkdir()
    (repo / "eval" / "reports" / "latest.json").write_text('{"nItems": 7}')
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("gcloud", "bq"):
        stub = bin_dir / name
        stub.write_text(STUB)
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return SimpleNamespace(
        repo=repo,
        bin=bin_dir,
        log=tmp_path / "calls.log",
        seen=tmp_path / "deploy-seen.txt",
        uploaded=tmp_path / "uploaded",
    )


def run_script(box, name: str, **env) -> subprocess.CompletedProcess:
    full = {
        "PATH": f"{box.bin}:/usr/bin:/bin",
        "HOME": str(box.repo),
        "PROJECT_ID": "say-it-back-test",
        "STUB_LOG": str(box.log),
        "STUB_SEEN": str(box.seen),
        "STUB_UPLOADED": str(box.uploaded),
        "STUB_REPO": str(box.repo),
        **env,
    }
    return subprocess.run(  # noqa: S603 - a fixed script under test with a stub PATH
        ["bash", str(box.repo / "deploy" / name)],  # noqa: S607
        env=full, capture_output=True, text=True, timeout=60, check=False, cwd=box.repo,
    )  # fmt: skip


def calls(box, prefix: str) -> list[str]:
    lines = box.log.read_text().splitlines() if box.log.exists() else []
    return [ln for ln in lines if ln.startswith(prefix)]


def roles_granted(box) -> list[str]:
    bound = calls(box, "gcloud projects add-iam-policy-binding")
    return sorted(
        part.split("=", 1)[1] for ln in bound for part in ln.split() if part.startswith("--role=")
    )


class TestBigQueryRole:
    BASE = ["roles/aiplatform.user", "roles/cloudtrace.agent", "roles/datastore.user"]

    def test_review_s13_no_bigquery_role_without_a_dataset(self, sandbox):
        result = run_script(sandbox, "01_setup_project.sh", BQ_DATASET="")
        assert result.returncode == 0, result.stderr
        assert roles_granted(sandbox) == self.BASE
        assert calls(sandbox, "bq ") == []  # and no dataset is created

    def test_with_a_dataset_the_role_is_granted_and_the_dataset_made(self, sandbox):
        result = run_script(sandbox, "01_setup_project.sh", BQ_DATASET="analytics")
        assert result.returncode == 0, result.stderr
        assert roles_granted(sandbox) == sorted([*self.BASE, "roles/bigquery.dataEditor"])
        assert any(" mk " in line for line in calls(sandbox, "bq "))


class TestTheFirestoreIndex:
    CREATE = "gcloud firestore indexes composite create"

    def test_it_is_created_when_no_such_index_exists(self, sandbox):
        result = run_script(sandbox, "01_setup_project.sh", STUB_INDEX="")
        assert result.returncode == 0, result.stderr
        (created,) = calls(sandbox, self.CREATE)
        for flag in (
            "--collection-group=briefings",
            "--field-config=field-path=owner,order=ascending",
            "--field-config=field-path=createdAt,order=descending",
            "--database=(default)",
            "--project say-it-back-test",
        ):
            assert flag in created, flag
        assert created.index("field-path=owner") < created.index("field-path=createdAt")

    def test_it_is_not_created_again_when_it_exists_so_the_script_can_run_twice(self, sandbox):
        result = run_script(sandbox, "01_setup_project.sh", STUB_INDEX=INDEX_NAME)
        assert result.returncode == 0, result.stderr
        assert calls(sandbox, self.CREATE) == []
        assert "already exists" in result.stdout and "owner, createdAt" in result.stdout

    def test_the_probe_asks_for_exactly_this_index(self, sandbox):
        run_script(sandbox, "01_setup_project.sh", STUB_INDEX=INDEX_NAME)
        (asked,) = calls(sandbox, "gcloud firestore indexes composite list")
        for part in (
            "collectionGroups/briefings/indexes/",
            "queryScope=COLLECTION",
            "fields[0].fieldPath=owner",
            "fields[0].order=ASCENDING",
            "fields[1].fieldPath=createdAt",
            "fields[1].order=DESCENDING",
        ):
            assert part in asked, part

    def test_it_is_the_index_the_stores_list_query_needs(self, sandbox):
        """The query the Firestore store runs for a caller's list, as the fake saw it, against the
        index the script creates: change one and this fails until the other follows."""
        run_script(sandbox, "01_setup_project.sh", STUB_INDEX="")
        (created,) = calls(sandbox, self.CREATE)
        fields = [
            dict(p.split("=", 1) for p in arg.removeprefix("--field-config=").split(","))
            for arg in created.split()
            if arg.startswith("--field-config=")
        ]
        direction = {"ascending": "ASCENDING", "descending": "DESCENDING"}
        index = [(f["field-path"], direction[f["order"]]) for f in fields]

        store = FakeBackedStore()
        run_sync(store.recent(20, "a" * 64))
        (query,) = store.fake.queries
        needed = [(f, "ASCENDING") for f, op in query.equals if op == "=="] + [query.order]
        assert query.collection == BRIEFINGS == "briefings"
        assert index == needed == [("owner", "ASCENDING"), ("createdAt", "DESCENDING")]


class TestEvalDataInTheImage:
    def test_the_test_set_and_report_are_in_the_build_folder_when_gcloud_uploads_it(self, sandbox):
        result = run_script(sandbox, "02_deploy_backend.sh")
        assert result.returncode == 0, result.stderr
        seen = sandbox.seen.read_text().splitlines()
        assert seen[1:] == [
            "./.gitkeep",
            "./reports/latest.json",
            "./testset/audio/a.wav",
            "./testset/items.json",
        ]

    def test_the_copy_is_removed_afterwards_and_the_placeholder_stays(self, sandbox):
        run_script(sandbox, "02_deploy_backend.sh")
        left = sorted(p.name for p in (sandbox.repo / "backend" / "eval_data").iterdir())
        assert left == [".gitkeep"]

    def test_a_failed_deploy_still_cleans_up(self, sandbox):
        result = run_script(sandbox, "02_deploy_backend.sh", STUB_FAIL_DEPLOY="1")
        assert result.returncode != 0
        assert sorted(p.name for p in (sandbox.repo / "backend" / "eval_data").iterdir()) == [
            ".gitkeep"
        ]

    def test_a_missing_report_is_a_warning_not_a_failure(self, sandbox):
        shutil.rmtree(sandbox.repo / "eval" / "reports")
        result = run_script(sandbox, "02_deploy_backend.sh")
        assert result.returncode == 0, result.stderr
        assert "eval/reports/latest.json not found" in result.stderr
        assert "./reports/latest.json" not in sandbox.seen.read_text()
        assert "./testset/items.json" in sandbox.seen.read_text()

    def test_no_eval_folder_at_all_still_deploys(self, sandbox):
        shutil.rmtree(sandbox.repo / "eval")
        result = run_script(sandbox, "02_deploy_backend.sh")
        assert result.returncode == 0, result.stderr
        assert sandbox.seen.read_text().splitlines()[1:] == ["./.gitkeep"]

    def test_a_copy_left_by_an_interrupted_run_is_not_shipped(self, sandbox):
        stale = sandbox.repo / "backend" / "eval_data" / "testset"
        stale.mkdir()
        (stale / "old-run.json").write_text("{}")
        run_script(sandbox, "02_deploy_backend.sh")
        assert "old-run.json" not in sandbox.seen.read_text()

    def test_nothing_is_staged_when_the_script_refuses_to_run(self, sandbox):
        (sandbox.repo / "backend" / ".gcloudignore").unlink()
        result = run_script(sandbox, "02_deploy_backend.sh")
        assert result.returncode != 0 and "backend/.gcloudignore is missing" in result.stderr
        assert not (sandbox.repo / "backend" / "eval_data" / "testset").exists()
        assert calls(sandbox, "gcloud run deploy") == []

    def test_the_deploy_command_keeps_its_shape(self, sandbox):
        run_script(sandbox, "02_deploy_backend.sh")
        (deploy,) = calls(sandbox, "gcloud run deploy")
        for part in (
            "say-it-back-api",
            "--source " + str(sandbox.repo / "backend"),
            "--allow-unauthenticated",
            "--timeout=900",
            "--session-affinity",
            "--service-account say-it-back-run@say-it-back-test.iam.gserviceaccount.com",
        ):
            assert part in deploy, part
        assert len(calls(sandbox, "gcloud run services update")) == 1  # SIB_PUBLIC_WS_BASE

    def test_the_new_settings_are_set_on_the_service(self, sandbox):
        run_script(sandbox, "02_deploy_backend.sh")
        (deploy,) = calls(sandbox, "gcloud run deploy")
        assert "@SIB_DAILY_CALLS_PER_IP=100@" in deploy
        assert "@SIB_TRUSTED_PROXY_HOPS=1@" in deploy
        assert "SIB_API_DOCS" not in deploy  # docs stay off in the cloud


class TestTheBuildContext:
    def test_the_dockerfile_copies_the_staged_folder_to_where_the_service_reads_it(self):
        text = (BACKEND / "Dockerfile").read_text()
        assert "COPY eval_data ./eval" in text and "SIB_EVAL_DIR=/app/eval" in text
        assert (BACKEND / "eval_data").is_dir()  # tracked through its placeholder

    def test_what_gcloud_uploads_is_the_layout_the_eval_endpoints_read(self, sandbox):
        """Seen from SIB_EVAL_DIR (the folder the image holds as /app/eval): the same code that
        serves endpoints 16 and 17 finds the test set and the report in what was uploaded."""
        from sayitback.evalset import EvalData

        assert run_script(sandbox, "02_deploy_backend.sh").returncode == 0
        data = EvalData(sandbox.uploaded)
        assert data.items_file()["version"] == "v" and data.latest_report() == {"nItems": 7}
        assert data.audio_path({"audio": "audio/a.wav"}).read_bytes() == b"RIFF"

    def test_the_ignore_files_let_the_staged_folder_into_the_build(self):
        for name in (".gcloudignore", ".dockerignore"):
            lines = [ln.strip() for ln in (BACKEND / name).read_text().splitlines()]
            assert not any(ln.startswith("eval_data") for ln in lines), name
        assert "eval_data/*" in (BACKEND / ".gitignore").read_text()  # and git keeps it out
