"""Minimal hello-agent example for unit-test compatibility."""


def run_agent() -> dict[str, str]:
    return {"status": "ok", "message": "Hello from AITBC"}


if __name__ == "__main__":
    print(run_agent())
