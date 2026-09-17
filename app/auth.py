import hashlib
import secrets


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return salt.hex() + ":" + digest.hex()


def check_password(password, encoded):
    salt, digest = encoded.split(":", 1)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000)
    return secrets.compare_digest(candidate.hex(), digest)
