"""Security fixes B, M1 (build-notes/36-security-fixes-b.md): in firebase mode roles are per site.

A member reaches a briefing only at a site where they hold a role. At any other site every route
that names the briefing answers the 404 of an unknown id, before any upload is read, creating one
is 403 `forbidden`, and the list and the CSV export hold only the member's own sites. An org admin
holds admin at every site, so reaches all. Device mode is unchanged.
"""

from __future__ import annotations

import csv
import io

import pytest

from sayitback.store import LocalStore
from tests.accounts_support import accounts, grant
from tests.fakes import FakeTtsClient
from tests.flow_support import round_1_scenario
from tests.helpers import PANEL, api_client, drive_to_round, error_of, make_app
from tests.test_ownership import briefing_routes

SG = PANEL
CHENNAI = {**PANEL, "siteId": "chennai", "workerLang": "hi"}
UNKNOWN = "b_zzzzzzzzzzzz"


def every_route(bid: str) -> dict[str, tuple[str, str, dict]]:
    """Every route that names a briefing: the ownership table, privacy's two, and TTS (12)."""
    base = f"/api/briefings/{bid}"
    return {
        **briefing_routes(bid),
        "record consent": ("POST", f"{base}/rounds/1/consent", {"json": {"given": True}}),
        "delete": ("DELETE", base, {}),
        "speak a line": ("POST", "/api/tts", {"json": {"briefingId": bid, "n": 1, "text": "x"}}),
    }


@pytest.fixture
def env(settings):
    """boss (org admin), sup (supervisor at sg only), officer (safety officer at chennai only),
    and a chennai briefing at round 1, made by boss."""
    env = accounts(settings, round_1_scenario())
    grant(env, "sup", {"sg": ["supervisor"]})
    grant(env, "officer", {"chennai": ["safety_officer"]})
    env.chennai, _ = drive_to_round(env.as_user("boss"), CHENNAI)
    return env


def listed(env, name: str, query: str = "") -> list[str]:
    return [b["id"] for b in env.as_user(name).get(f"/api/briefings{query}").json()["items"]]


def exported(env, name: str) -> set[str]:
    text = env.as_user(name).get("/api/export/briefings.csv").text
    return {row["briefingId"] for row in csv.DictReader(io.StringIO(text))}


class TestAnotherSitesBriefing:
    @pytest.mark.parametrize("name", list(every_route(UNKNOWN)))
    def test_every_route_answers_exactly_as_for_an_unknown_id(self, env, name):
        sup = env.as_user("sup")
        method, path, args = every_route(env.chennai)[name]
        refused = sup.request(method, path, **args)
        method, path, args = every_route(UNKNOWN)[name]
        unknown = sup.request(method, path, **args)

        assert error_of(refused) == (404, "not_found")
        assert refused.json() == unknown.json()

    def test_none_of_them_reads_a_model_or_changes_the_record(self, env):
        boss, sup = env.as_user("boss"), env.as_user("sup")
        before, calls = boss.get(f"/api/briefings/{env.chennai}").json(), len(env.llm.seen)

        for method, path, args in every_route(env.chennai).values():
            sup.request(method, path, **args)

        assert boss.get(f"/api/briefings/{env.chennai}").json() == before  # not even deleted
        assert len(env.llm.seen) == calls

    def test_an_upload_to_it_is_never_read(self, env):
        sup = env.as_user("sup")
        junk = [("q1", ("q1.wav", b"not a wav", "audio/wav"))]
        check = sup.post(f"/api/briefings/{env.chennai}/rounds/1/check", files=junk)
        hazard = sup.post(
            f"/api/briefings/{env.chennai}/hazards", files=[("audio", ("h.wav", b"x", "audio/wav"))]
        )
        assert error_of(check) == (404, "not_found")  # not 415: refused before parsing
        assert error_of(hazard) == (404, "not_found")

    def test_the_org_admin_and_the_sites_own_members_reach_it(self, env):
        for name in ("boss", "officer"):
            client = env.as_user(name)
            assert client.get(f"/api/briefings/{env.chennai}/verify").json()["ok"] is True
        decided = env.as_user("officer").post(
            f"/api/briefings/{env.chennai}/decision", json={"value": "no_go"}
        )
        assert decided.status_code == 200, decided.text

    def test_a_role_taken_away_takes_the_briefing_away_at_the_next_request(self, env):
        grant(env, "sup", {"sg": ["supervisor"], "chennai": ["supervisor"]})
        assert env.as_user("sup").get(f"/api/briefings/{env.chennai}").status_code == 200
        grant(env, "sup", {"sg": ["supervisor"]})
        assert error_of(env.as_user("sup").get(f"/api/briefings/{env.chennai}")) == (
            404,
            "not_found",
        )


class TestCreating:
    def test_only_at_a_site_where_the_member_holds_a_role(self, env):
        sup, officer = env.as_user("sup"), env.as_user("officer")

        assert error_of(sup.post("/api/briefings", json=CHENNAI)) == (403, "forbidden")
        assert error_of(officer.post("/api/briefings", json=SG)) == (403, "forbidden")
        assert sup.post("/api/briefings", json=SG).status_code == 200
        assert officer.post("/api/briefings", json=CHENNAI).status_code == 200
        assert len(listed(env, "boss")) == 3  # the chennai fixture's and the two allowed

    def test_the_org_admin_creates_at_every_site(self, env):
        boss = env.as_user("boss")
        assert {boss.post("/api/briefings", json=b).status_code for b in (SG, CHENNAI)} == {200}


class TestListAndExport:
    def test_each_member_lists_only_their_sites_and_the_org_admin_all(self, env):
        sg = env.as_user("sup").post("/api/briefings", json=SG).json()["id"]

        assert listed(env, "sup") == [sg]
        assert listed(env, "officer") == [env.chennai]
        assert set(listed(env, "boss")) == {sg, env.chennai}

    def test_the_limit_counts_the_members_own_sites(self, env):
        """The org's newer briefings at another site never push a member's own out of the page."""
        sg = env.as_user("sup").post("/api/briefings", json=SG).json()["id"]
        for _ in range(3):
            env.as_user("boss").post("/api/briefings", json=CHENNAI)

        assert listed(env, "sup", "?limit=1") == [sg]
        assert len(listed(env, "boss", "?limit=2")) == 2

    def test_the_csv_export_holds_only_the_members_sites(self, env):
        sg, _ = drive_to_round(env.as_user("sup"), SG)  # a row per step: the steps are confirmed

        assert exported(env, "sup") == {sg}
        assert exported(env, "officer") == {env.chennai}
        assert exported(env, "boss") == {sg, env.chennai}


class TestDeviceModeIsUnchanged:
    def test_a_device_reaches_its_briefings_at_every_site(self, settings):
        app, *_ = make_app(settings, round_1_scenario(), tts_client=FakeTtsClient())
        device = api_client(app)
        made = {device.post("/api/briefings", json=b).json()["id"] for b in (SG, CHENNAI)}

        assert {b["id"] for b in device.get("/api/briefings").json()["items"]} == made
        assert {device.get(f"/api/briefings/{bid}").status_code for bid in made} == {200}

    def test_it_reads_nothing_more_for_a_briefing_route(self, settings):
        store = LocalStore(settings.data_dir)
        app, *_ = make_app(settings, store=store)
        device = api_client(app)
        bid = device.post("/api/briefings", json=CHENNAI).json()["id"]
        reads, real = [], store.get

        async def counted(briefing_id):
            reads.append(briefing_id)
            return await real(briefing_id)

        store.get = counted  # type: ignore[method-assign]
        assert device.get(f"/api/briefings/{bid}").status_code == 200
        assert reads == [bid]  # the handler's own read, as before
