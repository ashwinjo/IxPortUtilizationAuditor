"""Tests for on-demand Explorer refresh helpers (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collector.ports_client import POLL_PORTS_PATH, trigger_ports_poll
from collector.session_ports_client import POLL_TRIGGER_PATH, trigger_session_poll
from collector.true_port_utilization import refresh_settle_seconds


def test_refresh_settle_seconds_default():
    assert refresh_settle_seconds() == 3.0
    assert refresh_settle_seconds(0) == 0.0
    assert refresh_settle_seconds(1.5) == 1.5


def test_trigger_ports_poll_posts_empty_body():
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"ok": true}'
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("collector.ports_client.urllib.request.urlopen", return_value=mock_resp) as open_mock:
        result = trigger_ports_poll("http://inventory:3001", timeout=10.0)

    assert result == {"ok": True}
    req = open_mock.call_args[0][0]
    assert req.full_url == f"http://inventory:3001{POLL_PORTS_PATH}"
    assert req.method == "POST"
    assert req.data == b""


def test_trigger_ports_poll_empty_response_body():
    mock_resp = MagicMock()
    mock_resp.read.return_value = b""
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("collector.ports_client.urllib.request.urlopen", return_value=mock_resp):
        assert trigger_ports_poll("http://inventory:3001", timeout=5.0) == {}


@pytest.mark.asyncio
async def test_trigger_session_poll_posts_trigger_path():
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={"triggered": True})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.close = AsyncMock()

    result = await trigger_session_poll(
        "http://sessions:8080",
        session=mock_session,
        timeout=15.0,
    )

    assert result == {"triggered": True}
    mock_session.post.assert_called_once()
    call_args, call_kwargs = mock_session.post.call_args
    assert call_args[0] == f"http://sessions:8080{POLL_TRIGGER_PATH}"
    assert call_kwargs["headers"] == {"Accept": "application/json"}
    mock_session.close.assert_not_awaited()
