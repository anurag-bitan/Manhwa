import unittest
from unittest.mock import patch

from core.auth import verify_firebase_token


class FirebaseTokenVerifierTests(unittest.TestCase):
    @patch("core.auth.firebase_auth.verify_id_token")
    @patch("core.auth._firebase_ready", return_value=True)
    def test_accepts_valid_id_token(self, _ready, mock_verify):
        mock_verify.return_value = {
            "uid": "firebase-uid-123",
            "email": "user@example.com",
        }
        claims = verify_firebase_token("valid-token")
        self.assertEqual(claims["uid"], "firebase-uid-123")

    @patch("core.auth.firebase_auth.verify_id_token")
    @patch("core.auth._firebase_ready", return_value=True)
    def test_rejects_token_without_subject(self, _ready, mock_verify):
        mock_verify.return_value = {"email": "user@example.com"}
        with self.assertRaises(ValueError):
            verify_firebase_token("bad-token")

    def test_rejects_empty_token(self):
        with self.assertRaises(ValueError):
            verify_firebase_token("")


if __name__ == "__main__":
    unittest.main()
