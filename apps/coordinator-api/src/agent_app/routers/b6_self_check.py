"""Self-check for B6 CI dependency reproducibility."""


def test_locked_install():
    with open("/opt/aitbc/.github/workflows/ci.yml") as f:
        content = f.read()
    assert "--locked" in content
    print("B6 self-check: CI uses poetry --locked.")


if __name__ == "__main__":
    test_locked_install()
