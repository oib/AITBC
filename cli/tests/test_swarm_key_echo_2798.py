"""AUDIT-EDGE-CLI-SWARM-KEY-ECHO (#2798): ``ipfs swarm-key`` echoed the
private swarm key into stdout/scrollback/CI logs even after --output had
persisted it to a 0600 file. The value is now masked once written.
"""


def test_swarm_result_data_masks_key_when_written_to_file():
    from aitbc_cli.commands.ipfs import _swarm_result_data

    masked = _swarm_result_data({}, "SECRETKEY", False, written_to_file=True)
    assert masked["swarm_key"] == "***"
    # without --output the JSON echo is the only delivery — key stays
    plain = _swarm_result_data({}, "SECRETKEY", False)
    assert plain["swarm_key"] == "SECRETKEY"
