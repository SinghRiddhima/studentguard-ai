"""DEMO authentication helpers.

LIMITATIONS: passwords are PBKDF2-hashed with a per-user salt, but there is no lockout, MFA, password
reset, HTTPS, or session expiry. Demo credentials are published in the README. NOT suitable for real
student data – use institutional SSO / a hardened auth provider for any real deployment."""
import hashlib
import hmac
import secrets

ITERATIONS = 150_000
ROLES = ("student", "counsellor", "admin")


def hash_password(password: str, salt_hex: str = None):
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return dk.hex(), salt.hex()


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt_hex)[0], hash_hex)


def require_role(user, *roles):
    if not user or user.get("role") not in roles:
        raise PermissionError(f"This action requires role: {', '.join(roles)}.")


def require_own_student(user, student_id):
    if not user or user.get("role") != "student" or user.get("student_id") != student_id:
        raise PermissionError("Students may only access their own records.")
