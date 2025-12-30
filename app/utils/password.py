# app/utils/password.py
from passlib.context import CryptContext
import hashlib

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    # normalize + pre-hash
    sha = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return pwd_ctx.hash(sha)

def verify_password(password: str, hashed: str) -> bool:
    sha = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return pwd_ctx.verify(sha, hashed)
