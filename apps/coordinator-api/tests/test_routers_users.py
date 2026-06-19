"""Tests for users router with Redis-backed sessions."""


def test_register_user(client):
    """Test user registration."""
    response = client.post(
        "/v1/register",
        json={
            "email": "test@example.com",
            "username": "testuser",
            "wallet_address": "aitbc_test123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    assert data["email"] == "test@example.com"
    assert "session_token" in data


def test_login_user(client):
    """Test user login."""
    response = client.post(
        "/v1/login",
        json={"wallet_address": "aitbc_login_test"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    assert "session_token" in data


def test_get_current_user(client):
    """Test getting current user profile."""
    # Register first
    reg_resp = client.post(
        "/v1/register",
        json={
            "email": "test2@example.com",
            "username": "testuser2",
            "wallet_address": "aitbc_test2",
        },
    )
    token = reg_resp.json()["session_token"]

    # Get profile
    profile_resp = client.get(f"/v1/users/me?token={token}")
    assert profile_resp.status_code == 200
    data = profile_resp.json()
    assert data["email"] == "test2@example.com"


def test_get_current_user_invalid_token(client):
    """Test getting profile with invalid token."""
    response = client.get("/v1/users/me?token=invalid-token")
    assert response.status_code == 401
    assert "Invalid or expired token" in response.json()["detail"]


def test_logout(client):
    """Test user logout."""
    # Register first
    reg_resp = client.post(
        "/v1/register",
        json={
            "email": "test3@example.com",
            "username": "testuser3",
            "wallet_address": "aitbc_test3",
        },
    )
    token = reg_resp.json()["session_token"]

    # Logout
    logout_resp = client.post(f"/v1/logout?token={token}")
    assert logout_resp.status_code == 200
    assert "Logged out successfully" in logout_resp.json()["message"]

    # Verify token is invalidated
    profile_resp = client.get(f"/v1/users/me?token={token}")
    assert profile_resp.status_code == 401
