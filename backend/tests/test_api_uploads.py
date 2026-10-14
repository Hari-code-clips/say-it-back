"""Audio endpoints at the boundary: the check upload and transcribe (TTS: test_tts_binding.py)."""

from __future__ import annotations

import json

from tests.fakes import silent_wav, tone_wav
from tests.helpers import (
    check_files,
    error_of,
    post_check,
)


class TestCheckUpload:
    def test_a_check_needs_at_least_one_wav_named_by_question_id(self, client, briefing):
        text_file = client.post(
            f"/api/briefings/{briefing}/rounds/1/check", files={"x": ("x.txt", b"hi", "text/plain")}
        )
        assert error_of(text_file)[0] == 415
        assert (
            error_of(client.post(f"/api/briefings/{briefing}/rounds/1/check", data={"meta": "{}"}))[
                0
            ]
            == 422
        )

    def test_a_file_for_an_unknown_question_is_422(self, client, briefing):
        assert error_of(post_check(client, briefing, 1, q9=tone_wav()))[0] == 422

    def test_at_most_three_files(self, client, briefing):
        files = check_files(q1=tone_wav(), q2=tone_wav(), q3=tone_wav(), q4=tone_wav())
        response = client.post(f"/api/briefings/{briefing}/rounds/1/check", files=files)
        assert response.status_code in (400, 422)

    def test_a_non_wav_upload_is_415(self, client, briefing):
        response = client.post(
            f"/api/briefings/{briefing}/rounds/1/check",
            files=[("q1", ("q1.webm", b"\x1aE\xdf\xa3 webm bytes" * 30, "audio/webm"))],
        )
        assert error_of(response) == (415, "unsupported_media_type")

    def test_a_file_over_3_mb_is_413(self, client, briefing):
        big = tone_wav(2.0)[:44] + b"\x01\x00" * (3 * 1024 * 1024 // 2 + 10)
        assert error_of(post_check(client, briefing, 1, q1=big))[0] in (413, 415)

    def test_a_clip_longer_than_a_minute_is_422(self, client, briefing):
        assert error_of(post_check(client, briefing, 1, q1=silent_wav(61.0, 8000)))[0] in (413, 422)

    def test_bad_meta_is_422(self, client, briefing):
        for meta in ("not json", json.dumps({"mode": "teleport"})):
            response = client.post(
                f"/api/briefings/{briefing}/rounds/1/check",
                files=check_files(q1=tone_wav()),
                data={"meta": meta},
            )
            assert error_of(response)[0] == 422

    def test_a_second_check_of_the_same_round_is_409(self, client, briefing):
        assert post_check(client, briefing, 1).status_code == 200
        assert error_of(post_check(client, briefing, 1)) == (409, "invalid_state")

    def test_an_unknown_round_is_404(self, client, briefing):
        assert error_of(post_check(client, briefing, 5)) == (404, "round_not_found")

    def test_an_unknown_briefing_is_404(self, client):
        assert error_of(post_check(client, "b_aaaaaaaaaaaa", 1)) == (404, "not_found")
        assert error_of(client.get("/api/briefings/not-a-briefing-id")) == (404, "not_found")
        assert error_of(client.get("/api/briefings/../../etc/passwd")) == (404, "not_found")


class TestTranscribeEndpoint:
    def post(self, client, audio=None, lang="en", name="audio"):
        files = {name: ("a.wav", audio if audio is not None else tone_wav(), "audio/wav")}
        return client.post("/api/transcribe", files=files, data={"lang": lang})

    def test_it_returns_the_verbatim_text(self, client):
        assert self.post(client).json() == {"text": "Isolate the breaker."}

    def test_the_language_must_be_in_the_catalog(self, client):
        assert error_of(self.post(client, lang="xx"))[0] == 422

    def test_audio_must_be_a_wav(self, client):
        assert error_of(self.post(client, audio=b"ID3 not a wav" * 20)) == (
            415,
            "unsupported_media_type",
        )

    def test_the_audio_field_is_required(self, client):
        assert self.post(client, name="file").status_code == 422
