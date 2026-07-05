from __future__ import annotations

import pytest

pytest_plugins = ["tests.integration.conftest"]

from tests.api.support import AuthTestContext, build_auth_test_client  # noqa: E402


@pytest.fixture
def auth_context(postgres_urls: dict[str, str]) -> AuthTestContext:
    return build_auth_test_client(postgres_urls)
