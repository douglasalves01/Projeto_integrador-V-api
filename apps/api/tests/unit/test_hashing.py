"""Unit tests for password hashing."""
import pytest

from app.auth.hashing import hash_password, verify_password


class TestPasswordHashing:
    def test_hash_differs_from_original(self):
        password = "mysecurepassword"
        hashed = hash_password(password)
        assert hashed != password

    def test_verify_correct_password(self):
        password = "mysecurepassword"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        password = "mysecurepassword"
        hashed = hash_password(password)
        assert verify_password("wrongpassword", hashed) is False

    def test_different_hashes_for_same_password(self):
        """bcrypt generates different salts each time."""
        password = "mysecurepassword"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2
        # But both should verify
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True

    def test_hash_min_length_password(self):
        password = "12345678"  # 8 chars minimum
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_hash_max_length_password(self):
        password = "a" * 128  # 128 chars maximum
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_hash_special_characters(self):
        password = "p@$$w0rd!#%^&*()"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_hash_unicode_password(self):
        password = "senhaçãoéàü123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
