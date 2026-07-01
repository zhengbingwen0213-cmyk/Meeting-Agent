import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from app.routes import validate_extracted_locations


class RouteValidationTest(unittest.TestCase):
    def test_validate_extracted_locations_rejects_missing_locations(self):
        extraction = SimpleNamespace(
            self_location="",
            friend_location="",
            missing_fields=["self_location", "friend_location", "city"],
        )

        with self.assertRaises(HTTPException) as raised:
            validate_extracted_locations(extraction)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(
            raised.exception.detail,
            "没有识别到两个地点，请重新录音并说清楚“我在...，朋友在...”",
        )

    def test_validate_extracted_locations_accepts_two_locations(self):
        extraction = SimpleNamespace(
            self_location="杭州东站",
            friend_location="杭州西站",
            missing_fields=[],
        )

        validate_extracted_locations(extraction)


if __name__ == "__main__":
    unittest.main()
