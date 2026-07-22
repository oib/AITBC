"""Self-check for B8 docs reconciliation."""


def test_docs_updated():
    with open("/opt/aitbc/AGENTS.md") as f:
        assert "v0.10.17" in f.read()
    with open("/opt/aitbc/docs/releases/STATUS.md") as f:
        assert "v0.10.17" in f.read()
    print("B8 self-check: v0.10.17 referenced in AGENTS.md and STATUS.md.")


if __name__ == "__main__":
    test_docs_updated()
