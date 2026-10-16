"""Export the existing layout proposals as three independently openable HTML files.

No application, API or database is involved. Source templates continue to use
the shared design system; the export only embeds their existing assets.
"""
from __future__ import annotations

import argparse
import base64
from html.parser import HTMLParser
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("a", "b", "c")
ASSETS = {
    "../static/design-system/theme.css": ("text/css", "static/design-system/theme.css"),
    "../static/design-system/components.css": ("text/css", "static/design-system/components.css"),
    "../static/design-system/layout.css": ("text/css", "static/design-system/layout.css"),
    "../static/design-system/design-system.js": ("text/javascript", "static/design-system/design-system.js"),
    "../static/design-system/shell.js": ("text/javascript", "static/design-system/shell.js"),
    "pianificazione-demo.js": ("text/javascript", "anteprime/pianificazione-demo.js"),
}


class AssetCheck(HTMLParser):
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and not attrs.get("src", "").startswith("data:"):
            raise ValueError("An exported script still depends on another file")
        if tag == "link" and not attrs.get("href", "").startswith("data:"):
            raise ValueError("An exported stylesheet still depends on another file")


def embedded_assets():
    result = {}
    for reference, (mime, path) in ASSETS.items():
        content = (ROOT / path).read_text(encoding="utf-8")
        if path.endswith("/theme.css"):
            # Offline exports use the system fallback already declared by theme.css.
            # Do not contact Google Fonts when the recipient opens a downloaded file.
            content, removed = re.subn(
                r"(?m)^@import url\('https://fonts\.googleapis\.com/[^']*'\);\s*",
                "", content,
            )
            if removed != 1:
                raise ValueError("Review the theme font import before exporting")
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        result[reference] = f"data:{mime};charset=utf-8;base64,{encoded}"
    return result


def export(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = embedded_assets()
    paths = []
    for variant in VARIANTS:
        content = (ROOT / "anteprime" / f"pianificazione-{variant}.html").read_text(encoding="utf-8")
        for reference, embedded in assets.items():
            attribute = "href" if ASSETS[reference][0] == "text/css" else "src"
            marker = f'{attribute}="{reference}"'
            if content.count(marker) != 1:
                raise ValueError(f"Expected one {reference} in variant {variant}")
            content = content.replace(marker, f'{attribute}="{embedded}"')
        # Data-URI external scripts preserve defer and execution ordering in head.
        # Inline scripts there would run before document.body exists.
        content = content.replace(
            "<body ", '<body data-preview-export="standalone" ', 1
        )
        parser = AssetCheck()
        parser.feed(content)
        parser.close()
        path = output_dir / f"pianificazione-{variant}.html"
        path.write_text(content, encoding="utf-8")
        paths.append(path)
        print(f"Exported {path.name}: {path.stat().st_size} bytes", flush=True)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "test-results" / "planning-html",
    )
    args = parser.parse_args()
    export(args.output_dir.resolve())


if __name__ == "__main__":
    main()
