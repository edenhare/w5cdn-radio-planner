"""Static UI integrity, HTML/CSS/JS validation, offline asset hygiene, and theme token tests.

Adapted directly from w5cdn-net-logger/tests/test_ui_integrity.py.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

from core.models.preferences import VALID_COCKPIT_THEMES

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_ROOT / "src" / "web" / "static"
INDEX_HTML = STATIC_DIR / "index.html"
STYLES_CSS = STATIC_DIR / "styles.css"
APP_JS = STATIC_DIR / "app.js"

HTML_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
    # SVG self-closing primitives
    "circle",
    "ellipse",
    "line",
    "path",
    "polygon",
    "polyline",
    "rect",
    "stop",
    "use",
}


class _IndexHtmlInspector(HTMLParser):
    """Extract element IDs, tag balance, and HTML safety attributes from index.html."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.ids: set[str] = set()
        self.duplicate_ids: list[str] = []
        self.inline_event_attrs: list[str] = []
        self.unsafe_links: list[str] = []
        self.tag_errors: list[str] = []
        self._stack: list[tuple[str, int]] = []

    def _check_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        el_id = attr_map.get("id", "")
        if el_id:
            if el_id in self.ids:
                self.duplicate_ids.append(el_id)
            self.ids.add(el_id)
        for key, val in attr_map.items():
            if key.startswith("on"):
                self.inline_event_attrs.append(f"<{tag} {key}=...> (line {self.getpos()[0]})")
            if key in {"href", "src"} and val.strip().lower().startswith("javascript:"):
                self.unsafe_links.append(f"<{tag} {key}={val!r}> (line {self.getpos()[0]})")
        if attr_map.get("target", "").lower() == "_blank":
            rel_tokens = set(attr_map.get("rel", "").lower().split())
            if "noopener" not in rel_tokens:
                self.unsafe_links.append(
                    f"<{tag} target='_blank'> missing rel='noopener' (line {self.getpos()[0]})"
                )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        low = tag.lower()
        self._check_attrs(low, attrs)
        if low not in HTML_VOID_TAGS:
            self._stack.append((low, self.getpos()[0]))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._check_attrs(tag.lower(), attrs)

    def handle_endtag(self, tag: str) -> None:
        low = tag.lower()
        if low in HTML_VOID_TAGS:
            return
        if not self._stack:
            self.tag_errors.append(f"Unexpected closing </{low}> at line {self.getpos()[0]}")
            return
        top_tag, top_line = self._stack[-1]
        if top_tag == low:
            self._stack.pop()
        else:
            self.tag_errors.append(
                f"Mismatched closing </{low}> at line {self.getpos()[0]} "
                f"(expected </{top_tag}> opened at line {top_line})"
            )

    def unclosed_tags(self) -> list[str]:
        return [f"<{t}> opened at line {ln}" for t, ln in self._stack]


def _inspect_index_html() -> _IndexHtmlInspector:
    inspector = _IndexHtmlInspector()
    inspector.feed(INDEX_HTML.read_text(encoding="utf-8"))
    inspector.close()
    return inspector


def test_all_dom_id_references_exist_in_index_html() -> None:
    inspector = _inspect_index_html()
    assert APP_JS.is_file(), "Missing src/web/static/app.js"
    script = APP_JS.read_text(encoding="utf-8")
    dynamic_ids = set(re.findall(r'\.id\s*=\s*["\']([A-Za-z0-9_-]+)["\']', script))
    dynamic_ids |= set(re.findall(r'id=["\']([A-Za-z0-9_-]+)["\']', script))

    refs = (
        set(re.findall(r'\$\(["\']([A-Za-z0-9_-]+)["\']\)', script))
        | set(re.findall(r'getElementById\(["\']([A-Za-z0-9_-]+)["\']\)', script))
    )
    missing = sorted(refs - (inspector.ids | dynamic_ids))
    assert not missing, f"DOM IDs referenced in app.js but missing from index.html: {missing}"


def test_html_structure_offline_assets_duplicate_ids_and_inline_handlers() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "/static/styles.css" in html, "index.html must link /static/styles.css"
    assert "/static/app.js" in html, "index.html must load /static/app.js"
    assert "/static/vendor/leaflet/leaflet.js" in html, "index.html must load local Leaflet JS"
    assert "/static/vendor/leaflet/leaflet.css" in html, "index.html must load local Leaflet CSS"

    # Offline-first: disallow external CDN script/stylesheet links
    for forbidden_cdn in ("cdn.tailwindcss.com", "unpkg.com", "fonts.googleapis.com", "cdn.jsdelivr.net"):
        assert forbidden_cdn not in html, f"Disallowed external CDN reference in index.html: {forbidden_cdn}"

    inspector = _inspect_index_html()
    assert not inspector.duplicate_ids, f"Duplicate HTML IDs: {inspector.duplicate_ids}"
    assert not inspector.tag_errors, f"HTML tag mismatch errors: {inspector.tag_errors[:5]}"
    assert not inspector.unclosed_tags(), f"Unclosed HTML tags: {inspector.unclosed_tags()[:5]}"
    assert not inspector.inline_event_attrs, f"Disallowed inline event handlers: {inspector.inline_event_attrs}"
    assert not inspector.unsafe_links, f"Unsafe HTML links: {inspector.unsafe_links}"


def test_javascript_syntax_and_safety() -> None:
    assert APP_JS.is_file(), "Missing src/web/static/app.js"
    script = APP_JS.read_text(encoding="utf-8")

    assert not re.search(r"\beval\s*\(", script), "Disallowed eval() call in app.js"
    assert not re.search(r"\bnew\s+Function\s*\(", script), "Disallowed new Function() in app.js"
    assert not re.search(r"\bdocument\.write\s*\(", script), "Disallowed document.write() in app.js"

    for match in re.finditer(r'target="_blank"[^>]{0,120}', script):
        snippet = match.group(0)
        assert "noopener" in snippet, f"target='_blank' missing noopener in JS template: {snippet}"

    node_bin = shutil.which("node")
    if node_bin:
        proc = subprocess.run(
            [node_bin, "--check", str(APP_JS)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"JavaScript syntax error in app.js:\n{proc.stderr}"


def test_no_hardcoded_colors_outside_theme_definitions_and_all_9_themes_present() -> None:
    assert STYLES_CSS.is_file(), "Missing src/web/static/styles.css"
    style = STYLES_CSS.read_text(encoding="utf-8")
    html = INDEX_HTML.read_text(encoding="utf-8")

    for theme in VALID_COCKPIT_THEMES:
        assert f'[data-theme="{theme}"]' in style, f"Missing CSS theme block for {theme}"
        assert f'data-theme-pick="{theme}"' in html, f"Missing theme picker card for {theme}"

    non_theme_css = re.sub(r":root[^{]*\{[^}]*\}", "", style)
    non_theme_css = re.sub(r"\.theme-swatch[^{]*\{[^}]*\}", "", non_theme_css)
    non_theme_css = re.sub(r"/\*[\s\S]*?\*/", "", non_theme_css)

    hex_colors = re.findall(r"#[0-9a-fA-F]{3,8}\b", non_theme_css)
    rgba_colors = re.findall(r"rgba?\([^)]+\)", non_theme_css)
    assert not hex_colors, f"Hardcoded hex colors outside theme blocks: {hex_colors}"
    assert not rgba_colors, f"Hardcoded rgb/rgba colors outside theme blocks: {rgba_colors}"


def test_desktop_icons_manifest_and_linux_shell_script_line_endings() -> None:
    """Verify PWA manifest, icon assets, and strict LF endings on Linux shell scripts."""
    for rel in ("manifest.webmanifest", "icon.svg", "icon.png", "icon.ico"):
        asset = STATIC_DIR / rel
        assert asset.is_file() and asset.stat().st_size > 0, f"Missing or empty static asset: {asset}"

    for script_rel in ("start.sh", "scripts/install_linux_desktop.sh"):
        script_path = PROJECT_ROOT / script_rel
        assert script_path.is_file(), f"Missing Linux script: {script_path}"
        raw = script_path.read_bytes()
        assert b"\r\n" not in raw, f"Linux script {script_rel} must use LF line endings, found CRLF"
        assert raw.startswith(b"#!/usr/bin/env bash\n"), f"Linux script {script_rel} missing bash shebang"
