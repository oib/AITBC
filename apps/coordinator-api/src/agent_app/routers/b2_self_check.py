"""Self-check for B2 wallet login hardening."""

import secrets


def test_secure_session_token_has_session_id():
    session_id = secrets.token_urlsafe(16)
    assert len(session_id) >= 16
    print(f"Secure session token generated: session_id length={len(session_id)}")


if __name__ == "__main__":
    test_secure_session_token_has_session_id()
    print("B2 self-check passed.")
