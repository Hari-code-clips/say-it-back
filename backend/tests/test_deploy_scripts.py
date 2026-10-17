"""deploy/01, 02 and 04 under a stub `gcloud`: what they would run, and in what state.

The scripts create billable resources, so they are never run for real here. A stub `gcloud` and `bq`
put on PATH record each call and answer the few questions the scripts ask (does the database exist,
is the index there, what is the service URL). These tests cover the changes of the security review:
the BigQuery role only with a dataset (S13), the composite index behind a caller's list of briefings,
and the evaluation data that the image has to carry. API v0.4 adds the pinned model ids, the daily
caps and minimum instances from config.sh, the webhook URLs (never printed) and the webhook secret
(only by name, through Secret Manager), and step 4, the permit-to-work stub.
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
  "gcloud firestore databases describe"*) [[ -z "${STUB_NO_FIRESTORE:-}" ]] || exit 1 ;;
  "gcloud run services describe"*) echo https://say-it-back-api-abc.a.run.app ;;
  "bq show"*) exit 1 ;; # the dataset does not exist yet
  "gcloud artifacts repositories describe"*) [[ -n "${STUB_AR_EXISTS:-}" ]] || exit 1 ;;
  "gcloud billing budgets list"*) printf '%s' "${STUB_BUDGET:-}" ;;
  "gcloud iam roles describe"*) [[ -z "${STUB_NO_TELEMETRY_ROLE:-}" ]] || exit 1 ;;
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
    stub = repo / "integrations" / "ptw-stub"
    stub.mkdir(parents=True)
    (stub / "Dockerfile").write_text("FROM scratch\n")
    (stub / ".gcloudignore").write_text(".venv/\n")
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
    BASE = [
        "roles/aiplatform.user",
        "roles/cloudtrace.agent",
        "roles/datastore.user",
        "roles/telemetry.tracesWriter",
    ]

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
        assert "@SIB_DAILY_CALLS_PER_IP=300@" in deploy
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


WEBHOOKS = "https://ptw.example.run.app/webhook,https://chat.googleapis.com/v1/spaces/S/messages?key=KEYVAL9&token=TOKVAL9"


def env_vars(box) -> dict[str, str]:
    """The --update-env-vars of the deploy, as the stub gcloud saw it (^@^-delimited)."""
    (deploy,) = calls(box, "gcloud run deploy")
    value = deploy.split("--update-env-vars ", 1)[1].split(" --", 1)[0]
    assert value.startswith("^@^")
    return dict(pair.split("=", 1) for pair in value[3:].split("@"))


class TestTheV04Settings:
    def test_the_model_ids_are_pinned_from_config(self, sandbox):
        assert run_script(sandbox, "02_deploy_backend.sh").returncode == 0
        env = env_vars(sandbox)
        assert (env["SIB_FLASH_MODEL"], env["SIB_JUDGE_B_MODEL"]) == (
            "gemini-3.8-flash",
            "gemini-3.1-flash-lite",
        )
        assert (env["SIB_LIVE_MODEL"], env["SIB_TTS_MODEL"]) == (
            "gemini-3.8-live",
            "gemini-3.8-flash-tts",
        )
        lines = (DEPLOY / "config.sh").read_text().splitlines()
        for name in ("FLASH_MODEL", "JUDGE_B_MODEL", "LIVE_MODEL", "TTS_MODEL"):
            i = next(i for i, ln in enumerate(lines) if ln.startswith(f"{name}="))
            comment = " ".join(ln.split("#", 1)[1].strip() for ln in lines[i : i + 2] if "#" in ln)
            assert "Check the exact Agent Platform id at deploy" in comment, name

    def test_each_pin_can_be_set_and_an_empty_judge_b_means_flash(self, sandbox):
        result = run_script(
            sandbox, "02_deploy_backend.sh", FLASH_MODEL="gemini-3.8-flash-001", JUDGE_B_MODEL=""
        )
        assert result.returncode == 0, result.stderr
        env = env_vars(sandbox)
        assert env["SIB_FLASH_MODEL"] == "gemini-3.8-flash-001" and env["SIB_JUDGE_B_MODEL"] == ""

    def test_a_model_id_that_is_not_one_is_refused(self, sandbox):
        result = run_script(sandbox, "02_deploy_backend.sh", LIVE_MODEL="gemini live; rm -rf /")
        assert result.returncode != 0 and "LIVE_MODEL is not a model id" in result.stderr
        assert calls(sandbox, "gcloud run deploy") == []

    def test_the_daily_caps_and_minimum_instances_come_from_config(self, sandbox):
        """v0.5: the defaults are sized for the judging window and the free-trial credit."""
        run_script(sandbox, "02_deploy_backend.sh")
        env = env_vars(sandbox)
        assert (env["SIB_DAILY_GEMINI_CALLS"], env["SIB_DAILY_CALLS_PER_IP"]) == ("600", "300")
        assert "--min-instances=1" in calls(sandbox, "gcloud run deploy")[0]
        text = (DEPLOY / "config.sh").read_text()
        assert "judging window" in text.split("MIN_INSTANCES=", 1)[1].split("\n\n", 1)[0]
        caps = text.split("# Daily cost bounds", 1)[1].split("\n\n", 1)[0]
        assert "free-trial credit" in caps and "a room of judges" in caps

    def test_lowered_after_judging(self, sandbox):
        result = run_script(
            sandbox,
            "02_deploy_backend.sh",
            DAILY_CALLS="150",
            DAILY_CALLS_PER_IP="50",
            MIN_INSTANCES="0",
        )
        assert result.returncode == 0, result.stderr
        env = env_vars(sandbox)
        assert (env["SIB_DAILY_GEMINI_CALLS"], env["SIB_DAILY_CALLS_PER_IP"]) == ("150", "50")
        assert "--min-instances=0" in calls(sandbox, "gcloud run deploy")[0]

    def test_the_v05_limits_reach_the_service(self, sandbox):
        assert run_script(sandbox, "02_deploy_backend.sh").returncode == 0
        env = env_vars(sandbox)
        assert env["SIB_RATE_LIMIT_PER_MIN"] == "120" and env["SIB_MAX_SOCKETS_PER_IP"] == "12"
        assert env["SIB_MAX_OUTPUT_TOKENS"] == "4096" and env["SIB_WEBHOOK_TIMEOUT_S"] == "5"
        assert env["SIB_TTS_LOCATION"] == "global"

    def test_extra_origins_are_added_to_the_allow_list(self, sandbox):
        result = run_script(
            sandbox, "02_deploy_backend.sh", EXTRA_ORIGINS="https://say-it-back-demo.web.app"
        )
        assert result.returncode == 0, result.stderr
        assert env_vars(sandbox)["SIB_ALLOWED_ORIGINS"] == (
            "https://say-it-back-test.web.app,https://say-it-back-test.firebaseapp.com,"
            "https://say-it-back-demo.web.app"
        )

    @pytest.mark.parametrize(
        "origin", ["http://plain.web.app", "https://a.web.app/path", "https://a.web.app,x"]
    )
    def test_an_origin_that_is_not_one_is_refused(self, sandbox, origin):
        result = run_script(sandbox, "02_deploy_backend.sh", EXTRA_ORIGINS=origin)
        assert result.returncode != 0 and "EXTRA_ORIGINS entries" in result.stderr
        assert calls(sandbox, "gcloud run deploy") == []

    @pytest.mark.parametrize(
        "name",
        [
            "DAILY_CALLS",
            "DAILY_CALLS_PER_IP",
            "MIN_INSTANCES",
            "PTW_MIN_INSTANCES",
            "RATE_LIMIT_PER_MIN",
            "MAX_SOCKETS_PER_IP",
            "MAX_OUTPUT_TOKENS",
        ],
    )
    def test_a_count_that_is_not_a_whole_number_is_refused(self, sandbox, name):
        result = run_script(sandbox, "02_deploy_backend.sh", **{name: "lots"})
        assert result.returncode != 0 and f"{name} must be a whole number" in result.stderr


class TestTheWebhooks:
    def test_no_urls_sets_an_empty_list_and_no_secret(self, sandbox):
        run_script(sandbox, "02_deploy_backend.sh")
        assert env_vars(sandbox)["SIB_WEBHOOK_URL"] == ""
        assert "--set-secrets" not in calls(sandbox, "gcloud run deploy")[0]

    def test_the_urls_are_set_but_never_printed(self, sandbox):
        result = run_script(sandbox, "02_deploy_backend.sh", WEBHOOK_URLS=WEBHOOKS)
        assert result.returncode == 0, result.stderr
        assert env_vars(sandbox)["SIB_WEBHOOK_URL"] == WEBHOOKS
        printed = result.stdout + result.stderr
        assert (
            "KEYVAL9" not in printed and "TOKVAL9" not in printed and "ptw.example" not in printed
        )
        assert "SIB_WEBHOOK_URL=<hidden>" in result.stderr

    @pytest.mark.parametrize(
        ("urls", "message"),
        [
            (
                "https://a.example/x,https://b.example/x,https://c.example/x,https://d.example/x",
                "at most 3",
            ),
            ("http://plain.example/webhook", "entry 1 is not https"),
            ("https://user@host.example/x", "may not contain '@'"),
        ],
    )
    def test_bad_urls_are_refused_without_printing_them(self, sandbox, urls, message):
        result = run_script(sandbox, "02_deploy_backend.sh", WEBHOOK_URLS=urls)
        assert result.returncode != 0 and message in result.stderr
        assert "example" not in result.stderr
        assert calls(sandbox, "gcloud run deploy") == []

    def test_the_secret_is_set_by_name_from_secret_manager(self, sandbox):
        result = run_script(
            sandbox, "02_deploy_backend.sh", WEBHOOK_SECRET_NAME="sib-webhook-secret"
        )
        assert result.returncode == 0, result.stderr
        (deploy,) = calls(sandbox, "gcloud run deploy")
        assert "--set-secrets SIB_WEBHOOK_SECRET=sib-webhook-secret:latest" in deploy
        assert "SIB_WEBHOOK_SECRET" not in env_vars(sandbox)  # never a plain variable
        (grant,) = calls(sandbox, "gcloud secrets add-iam-policy-binding")
        assert grant.startswith("gcloud secrets add-iam-policy-binding sib-webhook-secret ")
        assert "--role=roles/secretmanager.secretAccessor" in grant
        assert "serviceAccount:say-it-back-run@" in grant

    def test_both_secrets_go_in_one_set_secrets(self, sandbox):
        result = run_script(
            sandbox, "02_deploy_backend.sh", WEBHOOK_SECRET_NAME="hook", USE_DEVELOPER_API_KEY="1"
        )
        assert result.returncode == 0, result.stderr
        (deploy,) = calls(sandbox, "gcloud run deploy")
        assert (
            "--set-secrets GOOGLE_API_KEY=say-it-back-gemini-key:latest,SIB_WEBHOOK_SECRET=hook:latest"
            in deploy
        )
        assert deploy.count("--set-secrets") == 1


class TestThePermitToWorkStub:
    def test_it_refuses_to_deploy_without_the_shared_secret(self, sandbox):
        result = run_script(sandbox, "04_deploy_ptw_stub.sh")
        assert result.returncode != 0 and "WEBHOOK_SECRET_NAME is empty" in result.stderr
        assert calls(sandbox, "gcloud run deploy") == []

    def test_it_deploys_a_second_public_service_with_the_same_secret(self, sandbox):
        result = run_script(
            sandbox, "04_deploy_ptw_stub.sh", WEBHOOK_SECRET_NAME="sib-webhook-secret"
        )
        assert result.returncode == 0, result.stderr
        (deploy,) = calls(sandbox, "gcloud run deploy")
        for part in (
            "gcloud run deploy say-it-back-ptw ",
            "--source " + str(sandbox.repo / "integrations" / "ptw-stub"),
            "--allow-unauthenticated",
            "--set-secrets SIB_WEBHOOK_SECRET=sib-webhook-secret:latest",
            "--service-account say-it-back-ptw@say-it-back-test.iam.gserviceaccount.com",
            "--max-instances=1",
            "--min-instances=0",  # v0.5.1: permits persist in Firestore, so it may scale to zero
            "--set-env-vars PTW_STORE=firestore",
        ):
            assert part in deploy, part
        (grant,) = calls(sandbox, "gcloud secrets add-iam-policy-binding")
        assert "serviceAccount:say-it-back-ptw@" in grant and "secretAccessor" in grant
        assert "Permit board: https://say-it-back-api-abc.a.run.app/" in result.stdout
        assert "/webhook to WEBHOOK_URLS" in result.stdout

    def test_its_account_may_use_firestore_and_nothing_else_project_wide(self, sandbox):
        """v0.5.1: the stub keeps its permits in Firestore (collection `permits`)."""
        result = run_script(sandbox, "04_deploy_ptw_stub.sh", WEBHOOK_SECRET_NAME="s")
        assert result.returncode == 0, result.stderr
        bound = calls(sandbox, "gcloud projects add-iam-policy-binding")
        assert bound == [ln for ln in bound if "serviceAccount:say-it-back-ptw@" in ln]
        assert roles_granted(sandbox) == ["roles/datastore.user"]
        assert "--condition=None" in bound[0] and "say-it-back-test" in bound[0]

    def test_it_needs_the_firestore_database_01_creates(self, sandbox):
        result = run_script(
            sandbox, "04_deploy_ptw_stub.sh", WEBHOOK_SECRET_NAME="s", STUB_NO_FIRESTORE="1"
        )
        assert result.returncode != 0 and "Run deploy/01_setup_project.sh first" in result.stderr
        assert calls(sandbox, "gcloud run deploy") == []
        assert calls(sandbox, "gcloud projects add-iam-policy-binding") == []

    def test_it_needs_its_ignore_file(self, sandbox):
        (sandbox.repo / "integrations" / "ptw-stub" / ".gcloudignore").unlink()
        result = run_script(sandbox, "04_deploy_ptw_stub.sh", WEBHOOK_SECRET_NAME="s")
        assert result.returncode != 0 and ".gcloudignore is missing" in result.stderr

    def test_the_real_stub_folder_has_what_the_script_needs(self):
        stub = REPO / "integrations" / "ptw-stub"
        for name in ("Dockerfile", ".gcloudignore", "pyproject.toml", "uv.lock"):
            assert (stub / name).is_file(), name
        assert "tests/" in (stub / ".gcloudignore").read_text()
        assert (
            "$PORT" in (stub / "Dockerfile").read_text()
            or "${PORT" in (stub / "Dockerfile").read_text()
        )


class TestTheV05Setup:
    """v0.5: a non-interactive first deploy, telemetry, and an optional budget that ignores credits."""

    def test_the_artifact_registry_repository_is_created_when_missing(self, sandbox):
        assert run_script(sandbox, "01_setup_project.sh").returncode == 0
        (created,) = calls(sandbox, "gcloud artifacts repositories create")
        assert "cloud-run-source-deploy" in created and "--location=asia-south1" in created
        assert "--repository-format=docker" in created

    def test_an_existing_repository_is_left_alone(self, sandbox):
        assert run_script(sandbox, "01_setup_project.sh", STUB_AR_EXISTS="1").returncode == 0
        assert calls(sandbox, "gcloud artifacts repositories create") == []

    def test_the_apis_03_and_the_trace_exporter_need_are_enabled(self, sandbox):
        assert run_script(sandbox, "01_setup_project.sh").returncode == 0
        (enabled,) = [
            c for c in calls(sandbox, "gcloud services enable") if "run.googleapis.com" in c
        ]
        for api in (
            "firebase.googleapis.com",
            "firebaserules.googleapis.com",
            "telemetry.googleapis.com",
        ):
            assert api in enabled, api

    def test_no_budget_without_a_billing_account(self, sandbox):
        result = run_script(sandbox, "01_setup_project.sh")
        assert result.returncode == 0 and calls(sandbox, "gcloud billing budgets") == []
        assert "no budget alert created" in result.stderr

    def test_the_budget_ignores_credits_and_alerts_early(self, sandbox):
        result = run_script(sandbox, "01_setup_project.sh", BILLING_ACCOUNT="0123AB-4567CD-89EF01")
        assert result.returncode == 0, result.stderr
        (created,) = calls(sandbox, "gcloud billing budgets create")
        assert "--credit-types-treatment=exclude-all-credits" in created
        assert (
            "--budget-amount=28797INR" in created
            and "--filter-projects=projects/say-it-back-test" in created
        )
        assert created.count("--threshold-rule=") == 5 and "percent=0.10" in created
        assert (
            "--billing-project=say-it-back-test" in created
        )  # not gcloud's configured quota project

    def test_an_existing_budget_is_not_created_twice(self, sandbox):
        run_script(
            sandbox,
            "01_setup_project.sh",
            BILLING_ACCOUNT="0123AB-4567CD-89EF01",
            STUB_BUDGET="budgets/1",
        )
        assert calls(sandbox, "gcloud billing budgets create") == []

    def test_a_billing_account_that_is_not_one_is_refused(self, sandbox):
        result = run_script(sandbox, "01_setup_project.sh", BILLING_ACCOUNT="my account")
        assert result.returncode != 0 and "BILLING_ACCOUNT must look like" in result.stderr

    def test_the_stub_can_still_be_kept_warm(self, sandbox):
        """v0.5.1: PTW_MIN_INSTANCES defaults to 0 (permits persist in Firestore); 1 still works."""
        result = run_script(
            sandbox, "04_deploy_ptw_stub.sh", WEBHOOK_SECRET_NAME="s", PTW_MIN_INSTANCES="1"
        )
        assert result.returncode == 0, result.stderr
        assert "--min-instances=1" in calls(sandbox, "gcloud run deploy")[0]


class TestTheModelProbe:
    """deploy/probe_models.sh runs the backend's probe with exactly the ids and locations 02 deploys."""

    def test_it_probes_the_pinned_models_on_agent_platform(self, sandbox):
        uv = sandbox.bin / "uv"
        uv.write_text(
            "#!/usr/bin/env bash\n"
            'printf \'%s|%s|%s|%s|%s|%s\\n\' "$*" "$GOOGLE_GENAI_USE_ENTERPRISE" "$GOOGLE_CLOUD_PROJECT" '
            '"$SIB_JUDGE_B_MODEL" "$SIB_TTS_LOCATION" "$SIB_LIVE_LOCATION" >> "$STUB_LOG"\n'
        )
        uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
        result = run_script(sandbox, "probe_models.sh", TTS_LOCATION="us-central1")
        assert result.returncode == 0, result.stderr
        (probe,) = calls(sandbox, "run python -m sayitback.probe")
        assert probe == (
            "run python -m sayitback.probe --also-location us-central1|true|say-it-back-test|"
            "gemini-3.1-flash-lite|us-central1|us-central1"
        )


class TestTheDemoVideoLink:
    """config.sh refuses a DEMO_VIDEO_URL that is not an https link before any script does anything."""

    @pytest.mark.parametrize("url", ["javascript:alert(1)", "http://youtu.be/x", "https://a b"])
    def test_a_link_that_is_not_https_is_refused(self, sandbox, url):
        result = run_script(sandbox, "02_deploy_backend.sh", DEMO_VIDEO_URL=url)
        assert result.returncode != 0 and "DEMO_VIDEO_URL must be an https:// link" in result.stderr
        assert calls(sandbox, "gcloud run deploy") == []

    def test_an_https_link_is_accepted(self, sandbox):
        assert (
            run_script(
                sandbox, "02_deploy_backend.sh", DEMO_VIDEO_URL="https://youtu.be/abc"
            ).returncode
            == 0
        )

    def test_step_3_builds_it_into_the_page(self):
        text = (DEPLOY / "03_deploy_web.sh").read_text()
        assert 'VITE_DEMO_VIDEO_URL="$DEMO_VIDEO_URL" npm run build' in text
        assert "node noMock.ts dist" in text


class TestTheServiceRanges:
    """config.sh refuses values the service would reject at start-up, so a deploy never ends in a failed revision."""

    @pytest.mark.parametrize("value", ["0", "0.0", "10.5", "11", "abc", "-1"])
    def test_a_webhook_timeout_outside_0_to_10_is_refused(self, sandbox, value):
        result = run_script(sandbox, "02_deploy_backend.sh", WEBHOOK_TIMEOUT_S=value)
        assert (
            result.returncode != 0
            and "WEBHOOK_TIMEOUT_S must be above 0 and at most 10" in result.stderr
        )
        assert calls(sandbox, "gcloud run deploy") == []

    @pytest.mark.parametrize("value", ["0.5", "2.5", "10"])
    def test_a_webhook_timeout_in_range_is_accepted(self, sandbox, value):
        assert run_script(sandbox, "02_deploy_backend.sh", WEBHOOK_TIMEOUT_S=value).returncode == 0
        assert env_vars(sandbox)["SIB_WEBHOOK_TIMEOUT_S"] == value

    def test_an_output_ceiling_under_1024_is_refused(self, sandbox):
        result = run_script(sandbox, "02_deploy_backend.sh", MAX_OUTPUT_TOKENS="512")
        assert result.returncode != 0 and "MAX_OUTPUT_TOKENS must be at least 1024" in result.stderr

    def test_without_the_telemetry_role_setup_warns_and_goes_on(self, sandbox):
        result = run_script(sandbox, "01_setup_project.sh", STUB_NO_TELEMETRY_ROLE="1")
        assert result.returncode == 0, result.stderr
        assert "roles/telemetry.tracesWriter not found" in result.stderr
        assert "roles/telemetry.tracesWriter" not in roles_granted(sandbox)
