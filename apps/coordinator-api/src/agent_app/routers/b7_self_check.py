"""Self-check for B7 mypy suppressions."""


def test_no_suppressions():
    import subprocess

    result = subprocess.run(["bash", "scripts/ci/check-type-ignores.sh"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    print("B7 self-check: No blanket mypy suppressions remain.")


if __name__ == "__main__":
    test_no_suppressions()
