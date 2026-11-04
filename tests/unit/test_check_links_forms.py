"""#1028 pins: check_links must resolve titled, angle, reference and image
links, and percent-decode targets before the filesystem check."""

from __future__ import annotations

import importlib.util
import os

SPEC = importlib.util.spec_from_file_location(
    "check_links",
    os.path.join(os.path.dirname(__file__), "../../scripts/docs/check_links.py"),
)


def _load():
    mod = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(mod)
    return mod


def test_iter_targets_sees_all_forms():
    mod = _load()
    text = """
[plain](x/a.md)
[titled](x/b.md "a title")
[angle](<x/c.md>)
![img](x/d.png)
[ref1][r1] and [ref2][]

[r1]: x/e.md
[ref2]: x/f.md
"""
    targets = list(mod.iter_link_targets(text))
    for want in ["x/a.md", "x/b.md", "x/c.md", "x/d.png", "x/e.md", "x/f.md"]:
        assert want in targets, f"{want} not resolved"


def test_percent_decoded_target(tmp_path):
    mod = _load()
    (tmp_path / "my file.md").write_text("# ok")
    text = f"[link]({tmp_path.as_posix()}/my%20file.md)"
    targets = [mod.unquote(t).split("#", 1)[0] for t in mod.iter_link_targets(text)]
    assert targets == [str(tmp_path / "my file.md")]
    assert (tmp_path / "my file.md").exists()


def test_image_form_included():
    mod = _load()
    text = "![alt](x/g.png)"
    assert list(mod.iter_link_targets(text)) == ["x/g.png"]
