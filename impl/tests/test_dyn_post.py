"""Tests: dyn.post.v1 — posts that carry their work (docs/11-live-posts.md)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jsonschema  # noqa: E402  (available in CI; guarded below)

from dyn_post import (MAX_LIVE_EMBEDS, PostValueError, from_wire, highlight,
                      is_rtl, live_iframe, parse_post, render_post, to_wire)  # noqa: E402


SRC = """title: A post with work in it
lang: en
tags: demo, work

Hello from **the fleet**. See [the plan](https://github.com/roshpinacare-sys/dynamis).

```python
def settle(job):
    return usds(475)
```

```html live height=300
<p>app runs here</p>
```

פסקה בעברית עם כיוון משלה.
"""


class TestParse(unittest.TestCase):
    def test_title_tags_blocks(self):
        p = parse_post(SRC)
        self.assertEqual(p.title, "A post with work in it")
        self.assertEqual(p.tags, ["demo", "work"])
        kinds = [(b.kind, b.lang) for b in p.blocks]
        self.assertIn(("code", "python"), kinds)
        self.assertIn(("live", "html"), kinds)
        self.assertEqual(p.blocks[2].height, 300)

    def test_title_required(self):
        with self.assertRaises(PostValueError):
            parse_post("just text, no header")

    def test_unterminated_fence(self):
        with self.assertRaises(PostValueError):
            parse_post("title: x\n\n```python\nno end")


class TestRendering(unittest.TestCase):
    def test_text_is_escaped_no_raw_script(self):
        p = parse_post("title: x\n\n<script>alert(1)</script> plain text")
        page = render_post(p)
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)

    def test_links_sanitized(self):
        p = parse_post("title: x\n\n[a](javascript:alert(1)) [b](https://ok.example/x)")
        page = render_post(p)
        self.assertNotIn("javascript:", page)
        self.assertIn('href="https://ok.example/x"', page)

    def test_live_embed_sandboxed(self):
        p = parse_post(SRC)
        page = render_post(p)
        self.assertIn('<iframe class="dyn-live" sandbox="allow-scripts"', page)
        self.assertIn("Content-Security-Policy", page)
        self.assertIn("&#x27;none&#x27;", page)          # CSP inside srcdoc
        self.assertNotIn("allow-same-origin", page)
        self.assertNotIn("allow-top-navigation", page)

    def test_live_only_html(self):
        with self.assertRaises(PostValueError):
            render_post("title: x\n\n```python live\nprint(1)\n```")

    def test_live_size_cap(self):
        big = "x" * 70_000
        with self.assertRaises(PostValueError):
            live_iframe(big, 300)

    def test_live_count_cap(self):
        src = "title: x\n\n" + "\n\n```html live\n<p>app</p>\n```\n" * (MAX_LIVE_EMBEDS + 1)
        with self.assertRaises(PostValueError):
            render_post(src)

    def test_rtl_per_paragraph(self):
        page = render_post(parse_post(SRC))
        self.assertIn('<p dir="rtl">', page)
        self.assertIn('<p dir="ltr">', page)

    def test_is_rtl(self):
        self.assertTrue(is_rtl("שלום world"))
        self.assertFalse(is_rtl("hello שלום"))  # first strong char wins

    def test_highlight_smoke(self):
        self.assertIn('<span class="k">def</span>',
                      highlight("def f():\n    return 1", "python"))
        self.assertIn('<span class="t">', highlight("<div id='a'></div>", "html"))
        self.assertIn('<span class="c">', highlight("SELECT 1 -- note", "sql"))
        self.assertIn("plain &amp; simple", highlight("plain & simple", "madeuplang"))


class TestWire(unittest.TestCase):
    def test_round_trip_and_schema(self):
        p = parse_post(SRC)
        wire = to_wire(p, post_id="post-wire-1", author="agent-honest-1", day=3)
        self.assertEqual(wire["op"], "post")
        self.assertEqual(len(wire["embeds"]), 2)
        self.assertTrue(all(len(e["sha256"]) == 64 for e in wire["embeds"]))
        again = from_wire(wire)
        self.assertEqual(to_wire(again, post_id="post-wire-1",
                                 author="agent-honest-1", day=3), wire)

    def test_schema_validation(self):
        schema = json.loads((Path(__file__).resolve().parents[2]
                             / "schemas" / "post.schema.json").read_text())
        p = parse_post(SRC)
        wire = to_wire(p, post_id="post-wire-1", author="agent-honest-1", day=3)
        jsonschema.validate(wire, schema)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate({**wire, "op": "note"}, schema)

    def test_embed_hash_binds_bytes(self):
        import hashlib
        p = parse_post(SRC)
        wire = to_wire(p, post_id="post-wire-1", author="agent-honest-1", day=3)
        live = next(e for e in wire["embeds"] if e["kind"] == "live")
        code = next(b.content for b in p.blocks if b.kind == "live")
        self.assertEqual(live["sha256"], hashlib.sha256(code.encode()).hexdigest())


import json  # noqa: E402  (used in TestWire)


if __name__ == "__main__":
    unittest.main()
