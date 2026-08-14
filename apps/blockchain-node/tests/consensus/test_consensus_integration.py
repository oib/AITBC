"""
B14: Integration tests for consensus (full rounds, slashing, view change, persistence)
"""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole


def _make_consensus(n_validators: int = 4, chain_id: str = "test-int-chain") -> MultiValidatorPoA:
    """Create a MultiValidatorPoA with n validators, all PROPOSER role."""
    consensus = MultiValidatorPoA(chain_id)
    for i in range(n_validators):
        addr = f"0x{i:040x}"
        consensus.add_validator(addr, 1000.0)
        consensus.validators[addr].role = ValidatorRole.PROPOSER
    return consensus


def test_state_persistence_save_load():
    """save_state then load_state restores validators (mock the DB session)"""
    consensus = _make_consensus(3, chain_id="test-persist-chain")
    # The mock session simulates a DB row
    mock_row = Mock()
    mock_row.current_view = 0
    mock_row.current_sequence = 0
    mock_row.current_epoch = 0
    mock_row.validator_set_json = ""
    mock_row.slashing_events_json = "[]"

    mock_session = Mock()
    # query().filter_by().first() returns None on first save (insert), then row on load

    class MockQuery:
        def __init__(self, session):
            self.session = session

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return None  # no existing row

    mock_session.query = Mock(return_value=MockQuery(mock_session))

    import contextlib

    @contextlib.contextmanager
    def mock_session_scope(chain_id=""):
        yield mock_session

    # Patch session_scope in the database module
    from unittest.mock import patch

    with patch("aitbc_chain.database.session_scope", mock_session_scope):
        # Save state
        result = consensus.save_state()
        assert result is True
        # Verify session.add was called (insert path since no existing row)
        assert mock_session.add.called

    # Load back exactly what save_state wrote, rather than a hand-rolled copy of its shape.
    # The copy had drifted: it put the raw stake in, which stopped being JSON-serialisable
    # when V23-48 made it a Decimal -- and because nothing here compared the two, a mismatch
    # between the writer and this stand-in reader would never have failed the test.
    saved = mock_session.add.call_args[0][0]
    mock_row.validator_set_json = saved.validator_set_json
    mock_row.slashing_events_json = saved.slashing_events_json
    mock_row.current_view = 2
    mock_row.current_sequence = 5
    mock_row.current_epoch = 1

    class MockQueryLoad:
        def __init__(self):
            pass

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return mock_row

    mock_session_load = Mock()
    mock_session_load.query = Mock(return_value=MockQueryLoad())

    @contextlib.contextmanager
    def mock_session_scope_load(chain_id=""):
        yield mock_session_load

    # Create a fresh consensus to load into
    fresh_consensus = MultiValidatorPoA("test-persist-chain")
    with patch("aitbc_chain.database.session_scope", mock_session_scope_load):
        result = fresh_consensus.load_state()
        assert result is True
    # Validators should be restored
    assert len(fresh_consensus.validators) == 3
    # ...with their stakes intact and still Decimal, not merely counted
    for addr, original in consensus.validators.items():
        restored = fresh_consensus.validators[addr]
        assert isinstance(restored.stake, Decimal)
        assert restored.stake == original.stake
    assert fresh_consensus._pbft_view == 2
    assert fresh_consensus._pbft_sequence == 5
    assert fresh_consensus._current_epoch == 1


if __name__ == "__main__":
    pytest.main([__file__])
