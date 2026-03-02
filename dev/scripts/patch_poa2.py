with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "r") as f:
    content = f.read()

# Add CircuitBreaker class if missing, or import it if needed. It seems it was removed during our patching or wasn't there.
# Let's check if it exists in the original or another file. Ah, the test expects it in `aitbc_chain.consensus.poa`.
import re
has_cb = "class CircuitBreaker" in content

if not has_cb:
    cb_code = """
import time

class CircuitBreaker:
    def __init__(self, threshold: int, timeout: int):
        self._threshold = threshold
        self._timeout = timeout
        self._failures = 0
        self._last_failure_time = 0.0
        self._state = "closed"

    @property
    def state(self) -> str:
        if self._state == "open":
            if time.time() - self._last_failure_time > self._timeout:
                self._state = "half-open"
        return self._state

    def allow_request(self) -> bool:
        state = self.state
        if state == "closed":
            return True
        if state == "half-open":
            return True
        return False

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure_time = time.time()
        if self._failures >= self._threshold:
            self._state = "open"

    def record_success(self) -> None:
        self._failures = 0
        self._state = "closed"
"""
    # Insert it before PoAProposer
    content = content.replace("class PoAProposer:", cb_code + "\nclass PoAProposer:")
    
with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/consensus/poa.py", "w") as f:
    f.write(content)
