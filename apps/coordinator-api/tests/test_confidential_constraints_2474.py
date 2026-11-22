"""#2474: confidential/TEE job constraints must fail closed, not be ignored.

#2375 removed TEE attestation, which turned the old 503 refusal into a
silent acceptance: ``confidential: true`` and the removed ``tee_*`` keys
were dropped by ``extra="ignore"`` and the job dispatched as an ordinary,
normally priced job — a privacy claim with no mechanism. Creation now
rejects them (HTTP 422 via pydantic), while ``from_record`` keeps legacy
stored rows readable.
"""

import pytest
from pydantic import ValidationError

from coordinator_api.custom_types import (
    CONFIDENTIAL_UNSUPPORTED_MSG,
    RETIRED_CONSTRAINT_KEYS,
    Constraints,
)
from coordinator_api.schemas import JobCreate


@pytest.mark.parametrize("key", sorted(RETIRED_CONSTRAINT_KEYS))
@pytest.mark.parametrize("value", [True, False, "yes", 1])
def test_removed_tee_keys_rejected_on_presence(key, value):
    """Any of the three removed keys rejects, whatever the value."""
    with pytest.raises(ValidationError, match="not supported"):
        Constraints.model_validate({key: value})


def test_confidential_true_rejected():
    with pytest.raises(ValidationError, match="not supported"):
        Constraints.model_validate({"confidential": True})


def test_confidential_false_and_benign_extras_still_allowed():
    c = Constraints.model_validate({"confidential": False, "gpu": "a100", "unknown_future_key": 1})
    assert c.confidential is False
    assert c.gpu == "a100"


def test_job_create_rejects_confidential_constraints():
    """The request schema surfaces the rejection as a 422."""
    with pytest.raises(ValidationError):
        JobCreate(payload={"prompt": "x"}, constraints={"confidential": True})
    with pytest.raises(ValidationError):
        JobCreate(payload={"prompt": "x"}, constraints={"tee_enclave_id": "enc-1"})


def test_from_record_strips_legacy_retired_keys():
    """Stored rows written before #2375 stay readable and dispatchable."""
    c = Constraints.from_record(
        {
            "confidential": True,
            "tee_attestation_required": True,
            "tee_enclave_id": "enc-1",
            "required_enclave_measurement": "abc",
            "gpu": "a100",
        }
    )
    assert c.confidential is False
    assert c.gpu == "a100"


def test_error_message_names_the_removal():
    with pytest.raises(ValidationError) as exc_info:
        Constraints.model_validate({"tee_attestation_required": True})
    assert CONFIDENTIAL_UNSUPPORTED_MSG in str(exc_info.value)
