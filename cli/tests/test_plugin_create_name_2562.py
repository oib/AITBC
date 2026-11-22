"""AUDIT-PLUGIN-CREATE-NAME-1 (#2562): ``aitbc plugin create --name`` accepted
``../`` (writing the skeleton outside ``--output``) and quotes (producing an
unimportable .py while exiting 0). Names are now restricted to
``[A-Za-z0-9_-]+`` and the generated literals are JSON-escaped.
"""

import py_compile

from click.testing import CliRunner

from aitbc_cli.commands.plugin import plugin


def test_name_with_dotdot_does_not_escape_output(tmp_path):
    out = tmp_path / "plugins"
    result = CliRunner().invoke(
        plugin,
        ["create", "--name", "../escape", "--output", str(out)],
        obj={"output": "table"},
    )
    assert result.exit_code != 0
    assert "Invalid plugin name" in result.output
    # Nothing may be written outside --output.
    assert not (tmp_path / "escape.py").exists()
    assert not (tmp_path / "escape-manifest.json").exists()


def test_name_with_quote_is_rejected(tmp_path):
    result = CliRunner().invoke(
        plugin,
        ["create", "--name", 'bad"name', "--output", str(tmp_path)],
        obj={"output": "table"},
    )
    assert result.exit_code != 0
    assert "Invalid plugin name" in result.output
    assert not (tmp_path / 'bad"name.py').exists()


def test_valid_name_still_scaffolds_importable(tmp_path):
    result = CliRunner().invoke(
        plugin,
        ["create", "--name", "my-brand_2", "--output", str(tmp_path)],
        obj={"output": "table"},
    )
    assert result.exit_code == 0, result.output
    plugin_file = tmp_path / "my-brand_2.py"
    assert plugin_file.exists()
    py_compile.compile(str(plugin_file), doraise=True)
    assert (tmp_path / "my-brand_2-manifest.json").exists()
