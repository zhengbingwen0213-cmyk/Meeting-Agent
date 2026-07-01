import unittest

from app.services.deepseek_extractor import (
    DeepSeekExtractionError,
    extract_addresses_locally,
    friendly_deepseek_error,
)


class DeepSeekExtractorFallbackTest(unittest.TestCase):
    def test_extract_addresses_locally_from_common_meeting_sentence(self):
        result = extract_addresses_locally("我在杭州东站，朋友在杭州西站，我们该去哪里见面？")

        self.assertIsNotNone(result)
        self.assertEqual(result["self_location"], "杭州东站")
        self.assertEqual(result["friend_location"], "杭州西站")
        self.assertEqual(result["city"], "杭州")
        self.assertIn("local_rule_fallback", result["notes"])

    def test_friendly_deepseek_error_for_insufficient_balance(self):
        error = DeepSeekExtractionError(
            'DeepSeek HTTP 402: {"error":{"message":"Insufficient Balance","type":"unknown_error"}}'
        )

        self.assertEqual(
            friendly_deepseek_error(error),
            "DeepSeek 账户余额不足，请充值或更换 DEEPSEEK_API_KEY",
        )


if __name__ == "__main__":
    unittest.main()
