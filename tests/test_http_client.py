import unittest
from unittest.mock import Mock, patch

import requests

from ..network.HttpClient import HttpClient


class HttpClientSessionTests(unittest.TestCase):

    @patch.object(requests, "Session")
    @patch.object(requests, "request")
    def test_default_requests_do_not_create_a_session(
        self,
        request,
        session_factory,
    ):
        response = Mock()
        request.return_value = response

        client = HttpClient(timeout=7, user_agent="test-agent")
        result = client.request("GET", "https://example.com")

        self.assertIs(result, response)
        session_factory.assert_not_called()
        request.assert_called_once_with(
            method="GET",
            url="https://example.com",
            headers={"User-Agent": "test-agent"},
            timeout=7,
        )

    @patch.object(requests, "Session")
    def test_opted_in_requests_reuse_the_same_session(self, session_factory):
        session = session_factory.return_value
        response = Mock()
        session.request.return_value = response

        client = HttpClient(
            timeout=7,
            user_agent="test-agent",
            reuse_connections=True,
        )
        first_response = client.request("GET", "https://example.com/first")
        second_response = client.request(
            "POST",
            "https://example.com/second",
            headers={"X-Test": "value"},
        )

        session_factory.assert_called_once_with()
        self.assertIs(first_response, response)
        self.assertIs(second_response, response)
        self.assertEqual(session.request.call_count, 2)
        session.request.assert_any_call(
            method="GET",
            url="https://example.com/first",
            headers={"User-Agent": "test-agent"},
            timeout=7,
        )
        session.request.assert_any_call(
            method="POST",
            url="https://example.com/second",
            headers={
                "User-Agent": "test-agent",
                "X-Test": "value",
            },
            timeout=7,
        )

    @patch.object(requests, "Session")
    def test_close_releases_the_session_pool(self, session_factory):
        client = HttpClient(reuse_connections=True)

        client.close()

        session_factory.return_value.close.assert_called_once_with()

    @patch.object(requests, "Session")
    def test_temporary_session_is_isolated_from_parent(self, session_factory):
        client = HttpClient(timeout=6, user_agent="test-agent")

        temporary_client = client.temporary_session()

        self.assertIsNone(client.session)
        self.assertIs(
            temporary_client.session,
            session_factory.return_value,
        )
        self.assertEqual(temporary_client.timeout, 6)
        self.assertEqual(temporary_client.user_agent, "test-agent")


if __name__ == "__main__":
    unittest.main()
