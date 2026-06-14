from datetime import datetime, timedelta


USERS = {
    "admin@example.com": {"password": "admin123", "role": "admin"},
    "user@example.com": {"password": "user123", "role": "user"},
}


def login(email: str, password: str) -> dict:
    user = USERS.get(email)
    if user is None:
        return {"ok": False, "error": "user_not_found"}

    if user["password"] != password:
        return {"ok": False, "error": "invalid_password"}

    expires_at = datetime.utcnow() + timedelta(minutes=15)
    return {
        "ok": True,
        "email": email,
        "role": user["role"],
        "access_token": f"token-{email}",
        "expires_at": expires_at.isoformat(),
    }


def require_admin(session: dict) -> bool:
    if not session.get("ok"):
        return False
    return session.get("role") == "admin"


def delete_user(target_email: str, session: dict) -> dict:
    if not require_admin(session):
        return {"ok": False, "error": "permission_denied"}

    if target_email not in USERS:
        return {"ok": False, "error": "target_not_found"}

    if target_email == session.get("email"):
        return {"ok": False, "error": "cannot_delete_self"}

    del USERS[target_email]
    return {"ok": True, "deleted": target_email}


if __name__ == "__main__":
    user_session = login("user@example.com", "user123")
    print(delete_user("admin@example.com", user_session))

    admin_session = login("admin@example.com", "admin123")
    print(delete_user("user@example.com", admin_session))
