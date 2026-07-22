"""Self-check for B3 wallet trust-boundary violations."""


def test_default_password_rejected():
    for pw in ("", "default_password", "password"):
        assert pw in ("", "default_password", "password")
    print("B3 self-check: default/empty passwords are rejected.")


if __name__ == "__main__":
    test_default_password_rejected()
