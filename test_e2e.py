"""
Unit and Integration tests for the tool.
"""

import unittest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock

import selectors
from email_service import find_verification_email
from mock_server import MockServer
import httpx


class TestSelectors(unittest.TestCase):
    def test_selectors_defined(self):
        self.assertTrue(selectors.TEMP_MAIL_URL.startswith("https://10minutemail.net"))
        self.assertEqual(selectors.EMAIL_INPUT_SELECTOR, "#fe_text")
        self.assertEqual(selectors.INBOX_TABLE_SELECTOR, "#maillist")
        self.assertTrue(selectors.TARGET_EMAIL_INPUT_SELECTOR is not None)
        self.assertTrue(selectors.TARGET_SEND_CODE_BUTTON_SELECTOR is not None)
        self.assertTrue(selectors.ONBOARDING_HANDLE_ERROR_SELECTOR is not None)
        self.assertTrue(selectors.ONBOARDING_SAVE_BUTTON_SELECTOR is not None)
        self.assertTrue(selectors.ONBOARDING_RESIDENCE_SKIP_BUTTON_SELECTOR is not None)
        self.assertTrue(selectors.CIRCLE_FOLLOW_BUTTON_SELECTOR is not None)
        self.assertTrue(selectors.CIRCLE_JOIN_BUTTON_SELECTOR is not None)
        self.assertTrue(selectors.CIRCLE_CTA_CONTAINER_SELECTOR is not None)
        self.assertTrue(selectors.TARGET_LOGOUT_BUTTON_SELECTOR is not None)
        self.assertTrue(selectors.TARGET_CHANGE_EMAIL_BUTTON_SELECTOR is not None)


class TestEmailFiltering(unittest.TestCase):
    def test_find_verification_email_filters_welcome(self):
        messages = [
            {
                "sender": "no-reply@10minutemail.net",
                "subject": "Xin chào, chào mừng tới Email 10 Phút",
                "href": "readmail.html?mid=welcome"
            },
            {
                "sender": "support@targetsite.com",
                "subject": "Mã xác thực đăng ký tài khoản",
                "href": "readmail.html?mid=12345"
            }
        ]
        chosen = find_verification_email(messages)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["href"], "readmail.html?mid=12345")


class TestMockServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MockServer(port=5001)
        cls.server.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_mock_server_register_page(self):
        res = httpx.get("http://127.0.0.1:5001/register")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Đăng Ký Tài Khoản", res.text)
        self.assertIn("send-otp-btn", res.text)
        self.assertIn("verify-btn", res.text)

    def test_mock_server_otp_api(self):
        # 1. Send OTP
        res = httpx.post("http://127.0.0.1:5001/api/send-otp", json={"email": "test@domain.com"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("otp", data)
        otp = data["otp"]
        self.assertEqual(len(otp), 6)

        # 2. Verify Wrong OTP
        res_fail = httpx.post("http://127.0.0.1:5001/api/verify-otp", json={"email": "test@domain.com", "otp": "000000"})
        self.assertFalse(res_fail.json()["success"])

        # 3. Verify Correct OTP
        res_ok = httpx.post("http://127.0.0.1:5001/api/verify-otp", json={"email": "test@domain.com", "otp": otp})
        self.assertTrue(res_ok.json()["success"])


if __name__ == "__main__":
    unittest.main()
