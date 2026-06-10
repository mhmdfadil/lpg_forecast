"""
Model & operasi untuk admin_users.
"""
import bcrypt
from datetime import datetime, timezone
from app.supabase_client import get_supabase


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, AttributeError):
        return False


def get_admin_by_username(username: str):
    sb = get_supabase()
    res = (
        sb.table("admin_users")
        .select("*")
        .eq("username", username)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def get_admin_by_id(admin_id: str):
    sb = get_supabase()
    res = sb.table("admin_users").select("*").eq("id", admin_id).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


def touch_last_login(admin_id: str):
    sb = get_supabase()
    sb.table("admin_users").update(
        {"last_login_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", admin_id).execute()


def update_password(admin_id: str, new_password: str):
    sb = get_supabase()
    sb.table("admin_users").update(
        {"password_hash": hash_password(new_password)}
    ).eq("id", admin_id).execute()


def update_profile(admin_id: str, full_name: str = None, email: str = None):
    sb = get_supabase()
    payload = {}
    if full_name is not None:
        payload["full_name"] = full_name
    if email is not None:
        payload["email"] = email
    if payload:
        sb.table("admin_users").update(payload).eq("id", admin_id).execute()
