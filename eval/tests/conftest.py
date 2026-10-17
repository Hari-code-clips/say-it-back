"""--allow-missing-audio: let CI pass while the paid render is still to come, without hiding what is missing.

It skips exactly one test, the completeness check (every item has a current clip), and the skip reason
names how many clips are pending. Everything else still runs, including the check that the items' pending
marks match the clips on disk, so a clip cannot go missing or stale without the set saying so.
Remove the flag from CI once the render has run (eval/RUN_PAID.md).
"""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--allow-missing-audio", action="store_true", default=False,
        help="skip the every-clip-rendered check until the paid render runs (eval/RUN_PAID.md)",
    )


@pytest.fixture
def allow_missing_audio(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--allow-missing-audio"))
