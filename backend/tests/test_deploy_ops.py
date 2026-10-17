"""deploy/ production basics under the stub gcloud of test_deploy_scripts.py (never run for real):
automatic deletion (RETENTION_DAYS and the Firestore TTL policy of step 1), the data-region presets
(DATA_REGION), and step 5's email alerts (05_monitoring.sh), each idempotent and refusing bad
config before any gcloud call."""

from __future__ import annotations

import json

import pytest

from sayitback import retention
from sayitback.settings import MAX_RETENTION_DAYS
from sayitback.store.firestore_store import BRIEFINGS, OUTBOX
from tests import test_deploy_scripts as base
from tests.test_deploy_scripts import STUB, calls, env_vars, run_script

sandbox = base.sandbox  # the deploy sandbox fixture, under its own name here

# The extra questions steps 1 and 5 ask. A create answers with the name gcloud would print.
OPS_ARMS = """  "gcloud firestore fields ttls list"*) printf '%s' "${STUB_TTL:-}" ;;
  "gcloud components list"*) printf '%s\\n' ${STUB_COMPONENTS-alpha beta core} ;;
  "gcloud beta monitoring channels list"*) printf '%s' "${STUB_CHANNEL:-}" ;;
  "gcloud beta monitoring channels create"*) echo projects/say-it-back-test/notificationChannels/123 ;;
  "gcloud monitoring uptime list-configs"*) printf '%s' "${STUB_UPTIME:-}" ;;
  "gcloud monitoring uptime create"*) echo "projects/say-it-back-test/uptimeCheckConfigs/${4// /-}" ;;
  "gcloud alpha monitoring policies list"*) printf '%s' "${STUB_POLICY:-}" ;;
  "gcloud alpha monitoring policies create"*)
    for arg in "$@"; do [[ "$arg" != --policy-from-file=* ]] || cp "${arg#*=}" "$STUB_POLICIES/"; done
    echo projects/say-it-back-test/alertPolicies/9 ;;
  "gcloud secrets versions access"*) printf '%s' "${STUB_OUTBOX_TOKEN-OUTBOXTOKEN0123456789}" ;;
  "gcloud scheduler jobs describe"*) [[ -n "${STUB_JOB_EXISTS:-}" ]] || exit 1 ;;
"""
OPS_STUB = STUB.replace("esac", OPS_ARMS + "esac", 1)
CHANNEL = "projects/say-it-back-test/notificationChannels/123"
EMAIL = "ops@example.com"


@pytest.fixture
def box(sandbox, tmp_path):
    for name in ("gcloud", "bq"):
        (sandbox.bin / name).write_text(OPS_STUB)
    sandbox.policies = tmp_path / "policies"
    sandbox.policies.mkdir()
    return sandbox


def step5(box, **env):
    return run_script(box, "05_monitoring.sh", STUB_POLICIES=str(box.policies), **env)


class TestAutomaticDeletion:
    UPDATE = "gcloud firestore fields ttls update"

    def test_step_1_sets_a_ttl_policy_on_the_field_the_store_stamps(self, box):
        """On the briefings and, since 16 Oct, on the outbox (a delivery carries its briefing's expiry)."""
        result = run_script(box, "01_setup_project.sh")
        assert result.returncode == 0, result.stderr
        updates = calls(box, self.UPDATE)
        assert [u.split("--collection-group=")[1].split()[0] for u in updates] == [BRIEFINGS, OUTBOX]
        for update in updates:
            assert update.startswith(f"{self.UPDATE} {retention.FIELD} ") and "--enable-ttl" in update
            assert "--database=(default)" in update and "--project say-it-back-test" in update
        assert retention.FIELD == "expireAt" and BRIEFINGS == "briefings" and OUTBOX == "outbox"

    def test_an_existing_policy_is_left_alone(self, box):
        result = run_script(box, "01_setup_project.sh", STUB_TTL="expireAt")
        assert result.returncode == 0, result.stderr
        assert calls(box, self.UPDATE) == [] and "already exists" in result.stdout

    def test_retention_0_switches_the_policy_off_so_stamped_records_stay(self, box):
        result = run_script(box, "01_setup_project.sh", RETENTION_DAYS="0", STUB_TTL="expireAt")
        assert result.returncode == 0, result.stderr
        updates = calls(box, self.UPDATE)
        assert len(updates) == 2
        assert all("--disable-ttl" in u and "--enable-ttl" not in u for u in updates)

    def test_retention_0_without_a_policy_sets_none(self, box):
        assert run_script(box, "01_setup_project.sh", RETENTION_DAYS="0").returncode == 0
        assert calls(box, self.UPDATE) == []

    def test_the_days_reach_the_service(self, box):
        assert run_script(box, "02_deploy_backend.sh").returncode == 0
        assert env_vars(box)["SIB_RETENTION_DAYS"] == "90"
        box.log.unlink()
        assert run_script(box, "02_deploy_backend.sh", RETENTION_DAYS="30").returncode == 0
        assert env_vars(box)["SIB_RETENTION_DAYS"] == "30"

    @pytest.mark.parametrize(
        ("value", "message"),
        [
            (str(MAX_RETENTION_DAYS + 1), "RETENTION_DAYS must be 0 (keep) to 3650"),
            ("-1", "RETENTION_DAYS must be a whole number"),
            ("90d", "RETENTION_DAYS must be a whole number"),
        ],
    )
    def test_days_the_service_would_refuse_stop_before_any_call(self, box, value, message):
        result = run_script(box, "02_deploy_backend.sh", RETENTION_DAYS=value)
        assert result.returncode != 0 and message in result.stderr
        assert calls(box, "gcloud") == []

    def test_the_service_maximum_is_accepted(self, box):
        result = run_script(box, "02_deploy_backend.sh", RETENTION_DAYS=str(MAX_RETENTION_DAYS))
        assert result.returncode == 0, result.stderr


class TestTheDataRegion:
    def test_in_is_mumbai_by_default(self, box):
        assert run_script(box, "02_deploy_backend.sh").returncode == 0
        assert "--region asia-south1" in calls(box, "gcloud run deploy")[0]

    def test_sg_puts_cloud_run_firestore_and_the_images_in_singapore(self, box):
        result = run_script(box, "01_setup_project.sh", DATA_REGION="sg", STUB_NO_FIRESTORE="1")
        assert result.returncode == 0, result.stderr
        (database,) = calls(box, "gcloud firestore databases create")
        assert "--location=asia-southeast1" in database
        (repository,) = calls(box, "gcloud artifacts repositories create")
        assert "--location=asia-southeast1" in repository
        box.log.unlink()
        assert run_script(box, "02_deploy_backend.sh", DATA_REGION="sg").returncode == 0
        assert "--region asia-southeast1" in calls(box, "gcloud run deploy")[0]

    def test_gemini_stays_where_it_is_served(self, box):
        assert run_script(box, "02_deploy_backend.sh", DATA_REGION="sg").returncode == 0
        env = env_vars(box)
        assert env["GOOGLE_CLOUD_LOCATION"] == "global" and env["SIB_TTS_LOCATION"] == "global"
        assert env["SIB_LIVE_LOCATION"] == "us-central1"

    def test_a_database_in_another_region_stops_the_setup(self, box):
        """The stub's database is in asia-south1; a database cannot move."""
        result = run_script(box, "01_setup_project.sh", DATA_REGION="sg")
        assert result.returncode != 0 and "A database cannot move" in result.stderr
        assert calls(box, "gcloud iam service-accounts") == []

    @pytest.mark.parametrize("value", ["us", "IN", "asia-south1", " "])
    def test_a_preset_that_is_not_one_is_refused(self, box, value):
        result = run_script(box, "02_deploy_backend.sh", DATA_REGION=value)
        assert result.returncode != 0 and "DATA_REGION must be in" in result.stderr
        assert calls(box, "gcloud") == []


class TestTheAlerts:
    def test_without_an_address_nothing_is_created(self, box):
        result = step5(box)
        assert result.returncode == 0 and "ALERT_EMAIL is empty" in result.stderr
        assert calls(box, "gcloud") == []

    def test_it_creates_one_channel_two_checks_and_two_policies(self, box):
        result = step5(box, ALERT_EMAIL=EMAIL)
        assert result.returncode == 0, result.stderr
        (channel,) = calls(box, "gcloud beta monitoring channels create")
        assert "--type=email" in channel and f"--channel-labels=email_address={EMAIL}" in channel
        api, web = calls(box, "gcloud monitoring uptime create")
        assert "--resource-labels=host=say-it-back-api-abc.a.run.app,project_id=say-it-back-test" in api
        assert "--path=/api/health" in api and "--protocol=https" in api and "--period=5" in api
        assert "--resource-labels=host=say-it-back-test.web.app,project_id=say-it-back-test" in web
        assert "--path=/ " in web
        assert len(calls(box, "gcloud alpha monitoring policies create")) == 2
        assert calls(box, "gcloud services enable monitoring.googleapis.com")

    def test_the_site_down_policy_watches_both_checks(self, box):
        assert step5(box, ALERT_EMAIL=EMAIL).returncode == 0
        policy = json.loads((box.policies / "uptime.json").read_text())
        assert policy["notificationChannels"] == [CHANNEL] and policy["combiner"] == "OR"
        filters = [c["conditionThreshold"]["filter"] for c in policy["conditions"]]
        assert ['metric.label.check_id="say-it-back-API-health"' in f for f in filters] == [True, False]
        assert 'metric.label.check_id="say-it-back-web-app"' in filters[1]
        for condition in policy["conditions"]:
            threshold = condition["conditionThreshold"]
            assert "uptime_check/check_passed" in threshold["filter"]
            assert threshold["aggregations"][0]["crossSeriesReducer"] == "REDUCE_COUNT_FALSE"
            assert threshold["comparison"] == "COMPARISON_GT" and threshold["thresholdValue"] == 1

    def test_the_5xx_policy_is_a_ratio_on_the_api_service(self, box):
        assert step5(box, ALERT_EMAIL=EMAIL).returncode == 0
        policy = json.loads((box.policies / "server-errors.json").read_text())
        (condition,) = policy["conditions"]
        threshold = condition["conditionThreshold"]
        assert 'metric.labels.response_code_class="5xx"' in threshold["filter"]
        assert "5xx" not in threshold["denominatorFilter"]
        for part in ('service_name="say-it-back-api"', "run.googleapis.com/request_count"):
            assert part in threshold["filter"] and part in threshold["denominatorFilter"]
        assert threshold["thresholdValue"] == 0.05 and policy["notificationChannels"] == [CHANNEL]

    def test_a_second_run_creates_nothing(self, box):
        result = step5(
            box,
            ALERT_EMAIL=EMAIL,
            STUB_CHANNEL=CHANNEL,
            STUB_UPTIME="projects/say-it-back-test/uptimeCheckConfigs/existing-1",
            STUB_POLICY="projects/say-it-back-test/alertPolicies/1",
        )
        assert result.returncode == 0, result.stderr
        assert [c for c in calls(box, "gcloud") if " create" in c] == []
        assert result.stdout.count("already exists") == 3  # the channel and both policies

    def test_without_the_alpha_commands_it_stops_before_creating_anything(self, box):
        result = step5(box, ALERT_EMAIL=EMAIL, STUB_COMPONENTS="beta core")
        assert result.returncode != 0 and "gcloud components install alpha" in result.stderr
        assert [c for c in calls(box, "gcloud") if " create" in c or " enable" in c] == []

    @pytest.mark.parametrize(
        "address", ["ops", "ops@example.com,evil=1", "a b@example.com", "ops@example"]
    )
    def test_an_address_that_is_not_one_is_refused(self, box, address):
        result = step5(box, ALERT_EMAIL=address)
        assert result.returncode != 0 and "ALERT_EMAIL must be one email address" in result.stderr
        assert calls(box, "gcloud") == []


VENDOR = "https://permits.example.com/hook?key=VENDORKEY9"
TOKEN = "OUTBOXTOKEN0123456789"


class TestTheOutbox:
    """The pilot e-permit link (docs/EPERMIT_ADAPTER.md): off by default, secrets by name only, and
    since security fixes A refused by step 2, which deploys device mode only."""

    def test_off_by_default_and_set_off_explicitly(self, box):
        assert run_script(box, "02_deploy_backend.sh").returncode == 0
        env = env_vars(box)
        assert env["SIB_OUTBOX"] == "false" and env["SIB_PTW_URL"] == "" and env["SIB_PTW_FIELD_MAP"] == ""
        assert "--set-secrets" not in calls(box, "gcloud run deploy")[0]

    @pytest.mark.parametrize(
        "env",
        [
            {"OUTBOX": "1", "OUTBOX_TOKEN_SECRET_NAME": "sib-outbox-token"},
            {"PTW_URL": VENDOR},
            {
                "PTW_URL": VENDOR, "PTW_TOKEN_SECRET_NAME": "ptw-token",
                "PTW_FIELD_MAP": '{"permitId": "permit.ref", "go": "decision"}',
            },
        ],
    )  # fmt: skip
    def test_the_e_permit_link_stops_the_deploy_because_it_needs_accounts(self, box, env):
        """Security fixes A (H1): these scripts deploy device mode only, where no person stands
        behind a decision, so the link never reaches a service (which would refuse to start)."""
        result = run_script(box, "02_deploy_backend.sh", **env)
        assert result.returncode != 0
        assert "SIB_AUTH_MODE=firebase" in result.stderr and "build-notes/34-auth.md" in result.stderr
        assert calls(box, "gcloud") == []  # before any build, grant or deploy
        printed = result.stdout + result.stderr
        assert "VENDORKEY9" not in printed and "permits.example" not in printed

    @pytest.mark.parametrize(
        ("env", "message"),
        [
            ({"OUTBOX": "yes"}, "OUTBOX must be 0 or 1"),
            ({"OUTBOX": "1"}, "OUTBOX=1 needs OUTBOX_TOKEN_SECRET_NAME"),
            ({"PTW_TOKEN_SECRET_NAME": "t"}, "need PTW_URL"),
            ({"PTW_URL": "http://permits.example.com/hook"}, "PTW_URL must be one https:// URL"),
            ({"PTW_URL": "https://u@permits.example.com/hook"}, "PTW_URL must be one https:// URL"),
            ({"PTW_URL": VENDOR, "PTW_FIELD_MAP": "permitId=ref"}, "PTW_FIELD_MAP must be a one-line JSON"),
            ({"OUTBOX_TOKEN_SECRET_NAME": "bad name"}, "OUTBOX_TOKEN_SECRET_NAME must be a Secret"),
        ],
    )
    def test_bad_settings_stop_before_any_call_without_printing_the_url(self, box, env, message):
        result = run_script(box, "02_deploy_backend.sh", **env)
        assert result.returncode != 0 and message in result.stderr
        assert "permits.example" not in result.stderr and calls(box, "gcloud") == []

    def test_step_6_does_nothing_while_the_outbox_is_off(self, box):
        result = run_script(box, "06_outbox_retry.sh")
        assert result.returncode == 0 and "OUTBOX is 0" in result.stderr
        assert calls(box, "gcloud") == []

    def test_step_6_creates_the_retry_job_without_printing_the_token(self, box):
        result = run_script(box, "06_outbox_retry.sh", OUTBOX="1", OUTBOX_TOKEN_SECRET_NAME="sib-outbox-token")
        assert result.returncode == 0, result.stderr
        (job,) = calls(box, "gcloud scheduler jobs create http say-it-back-outbox-retry ")
        assert "--uri=https://say-it-back-api-abc.a.run.app/admin/outbox/retry" in job
        assert f"--headers=Authorization=Bearer {TOKEN}" in job and "--http-method=post" in job
        assert '--schedule=* * * * *' in job and "--location=asia-south1" in job
        assert TOKEN not in result.stdout + result.stderr
        assert "Authorization=Bearer <hidden>" in result.stderr

    def test_step_6_again_updates_the_job_so_a_rotated_token_reaches_it(self, box):
        result = run_script(
            box, "06_outbox_retry.sh", OUTBOX="1", OUTBOX_TOKEN_SECRET_NAME="t", STUB_JOB_EXISTS="1"
        )
        assert result.returncode == 0, result.stderr
        assert calls(box, "gcloud scheduler jobs create") == []
        (job,) = calls(box, "gcloud scheduler jobs update http say-it-back-outbox-retry ")
        assert f"--update-headers=Authorization=Bearer {TOKEN}" in job

    def test_step_6_refuses_a_token_a_header_cannot_carry(self, box):
        result = run_script(
            box, "06_outbox_retry.sh", OUTBOX="1", OUTBOX_TOKEN_SECRET_NAME="t",
            STUB_OUTBOX_TOKEN="short,token,with,commas",
        )  # fmt: skip
        assert result.returncode != 0 and "must be 16 or more" in result.stderr
        assert "commas" not in result.stdout + result.stderr
        assert calls(box, "gcloud scheduler") == []
