#!/usr/bin/env python3
"""
publish_map.py — Convert a composite TIFF into a DeepZoom tile set and
publish it to the nginx webserver directory.

Usage:
    python3 publish_map.py <source.tif> <slug> <title> [--city CITY] [--nav "Label:x,y,zoom;..."]

Example:
    python3 publish_map.py /Volumes/Files/claude/roanoke-1951/composite2.tif \
        Roanoke-1951 "Roanoke 1951" \
        --city Roanoke \
        --nav "Downtown:66000,60000,0.3;Norfolk & Western Shops:45000,50000,0.2"

Arguments:
    source.tif   Path to the source pyramidal (or flat) TIFF
    slug         Filename slug, e.g. Roanoke-1951  (no spaces)
    title        Human-readable title for the page

Options:
    --city CITY       City name for grouping in index.html (default: derived from slug)
    --nav NAVSPEC     Semicolon-separated nav buttons: "Label:x,y,zoom;..."
                      x,y are pixel coords in the source image; zoom is Zoomify-style
                      (smaller = more zoomed in, ~0.1-0.5 range)
    --webroot DIR     Nginx webroot (default: /Volumes/Files/claude/webserver)
    --tile-size N     DZI tile size in pixels (default: 256)
    --quality N       JPEG quality for tiles (default: 85)
    --dry-run         Print what would be done without doing it
"""

import argparse
import os
import re
import sys
import textwrap
import pyvips

WEBROOT_DEFAULT = '/Volumes/Files/claude/webserver'

# ── HTML template ────────────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <script src="../openseadragon/openseadragon.min.js"></script>
    <style>
        body {{ font-family: Optima, sans-serif; margin: 20px; }}
        h1 {{ margin-bottom: 10px; }}
        #viewer {{
            width: 95%;
            height: 700px;
            margin: auto;
            border: 1px solid #696969;
            background-color: #000000;
        }}
        .back {{ margin-bottom: 15px; }}
        .back a {{ color: #0066cc; }}
        .nav-buttons {{ text-align: center; padding: 10px; }}
        .nav-buttons input {{ margin: 3px; }}
    </style>
</head>
<body>
    <div class="back"><a href="../index.html">&larr; Back to index</a></div>
    <h1>{title}</h1>
{nav_html}
    <div id="viewer"></div>
    <script>
        var viewer = OpenSeadragon({{
            id: "viewer",
            prefixUrl: "../openseadragon/images/",
            tileSources: "{dzi_filename}",
            showNavigator: true,
            navigatorPosition: "BOTTOM_RIGHT"
        }});
{goto_js}
    </script>
</body>
</html>
"""

NAV_BUTTON_HTML = """\
    <div class="nav-buttons">
{buttons}
    </div>
"""

GOTO_JS = """\
        var imgWidth  = {img_width};
        var imgHeight = {img_height};

        function goTo(x, y, zoomifyZoom) {{
            var viewportX = x / imgWidth;
            var viewportY = y / imgWidth;
            var viewportPoint = new OpenSeadragon.Point(viewportX, viewportY);
            var osdZoom = 1 / zoomifyZoom;
            viewer.viewport.panTo(viewportPoint);
            viewer.viewport.zoomTo(osdZoom);
        }}
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_nav(navspec):
    """Parse 'Label:x,y,zoom;Label2:x2,y2,zoom2' into list of (label, x, y, zoom)."""
    buttons = []
    if not navspec:
        return buttons
    for part in navspec.split(';'):
        part = part.strip()
        if not part:
            continue
        m = re.match(r'^(.+?):(\d+),(\d+),([0-9.]+)$', part)
        if not m:
            print(f"WARNING: could not parse nav spec '{part}', skipping", file=sys.stderr)
            continue
        buttons.append((m.group(1).strip(), int(m.group(2)), int(m.group(3)), float(m.group(4))))
    return buttons


def city_from_slug(slug):
    """Derive city name from slug like 'Roanoke-1951' → 'Roanoke'."""
    return re.split(r'[-_]', slug)[0]


def find_city_section(html, city):
    """Return True if the city already has an <h2> section in index.html."""
    return bool(re.search(rf'<h2>{re.escape(city)}</h2>', html))


def inject_into_index(index_path, city, slug, title, dry_run=False):
    """Add a link to index.html, creating a new city section if needed."""
    with open(index_path) as f:
        html = f.read()

    link_line = f'        <li><a href="hires/{slug}-osd.html">{title}</a></li>\n'

    # Check if entry already exists
    if f'hires/{slug}-osd.html' in html:
        print(f"  index.html: entry for {slug} already present, skipping")
        return

    if find_city_section(html, city):
        # Insert after the <ul> that follows this city's <h2>
        pattern = rf'(<h2>{re.escape(city)}</h2>\s*<ul>)'
        replacement = rf'\1\n{link_line}'
        new_html = re.sub(pattern, replacement, html)
    else:
        # Insert a new city section before the closing </body>
        new_section = (
            f'\n    <h2>{city}</h2>\n'
            f'    <ul>\n'
            f'{link_line}'
            f'    </ul>\n'
        )
        new_html = html.replace('    <p class="note">', new_section + '    <p class="note">')

    if dry_run:
        print(f"  [DRY RUN] Would update index.html with link for {slug}")
        return

    with open(index_path, 'w') as f:
        f.write(new_html)
    print(f"  index.html: added entry for {slug}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source',     help='Source TIFF path')
    ap.add_argument('slug',       help='Filename slug, e.g. Roanoke-1951')
    ap.add_argument('title',      help='Human-readable page title')
    ap.add_argument('--city',     help='City name for index grouping (default: first word of slug)')
    ap.add_argument('--nav',      help='Nav buttons: "Label:x,y,zoom;..."')
    ap.add_argument('--webroot',  default=WEBROOT_DEFAULT)
    ap.add_argument('--tile-size',type=int, default=256)
    ap.add_argument('--quality',  type=int, default=85)
    ap.add_argument('--dry-run',  action='store_true')
    args = ap.parse_args()

    webroot  = args.webroot
    hires    = os.path.join(webroot, 'hires')
    dzi_base = os.path.join(hires, args.slug)          # hires/Roanoke-1951
    dzi_file = dzi_base + '.dzi'                        # hires/Roanoke-1951.dzi
    html_file = os.path.join(hires, f'{args.slug}-osd.html')
    index_file = os.path.join(webroot, 'index.html')
    city = args.city or city_from_slug(args.slug)
    nav_buttons = parse_nav(args.nav)

    print(f"publish_map.py")
    print(f"  source  : {args.source}")
    print(f"  slug    : {args.slug}")
    print(f"  title   : {args.title}")
    print(f"  city    : {city}")
    print(f"  webroot : {webroot}")
    print(f"  DZI out : {dzi_file}")
    print(f"  HTML out: {html_file}")
    print(f"  nav     : {nav_buttons or '(none)'}")
    print()

    # ── Step 1: Load source image ────────────────────────────────────────────
    print(f"Loading {args.source} ...")
    img = pyvips.Image.new_from_file(args.source, access='sequential')
    print(f"  {img.width} × {img.height} px, {img.bands} bands")

    # ── Step 2: Generate DZI tiles ───────────────────────────────────────────
    if os.path.exists(dzi_file) and not args.dry_run:
        print(f"  {dzi_file} already exists — skipping tile generation")
        print(f"  (delete it to regenerate)")
    else:
        print(f"Generating DZI tiles → {dzi_base} ...")
        if args.dry_run:
            print(f"  [DRY RUN] Would run dzsave with tile_size={args.tile_size} Q={args.quality}")
        else:
            img.dzsave(
                dzi_base,
                tile_size=args.tile_size,
                overlap=1,
                depth='onepixel',
                suffix=f'.jpg[Q={args.quality}]',
            )
            print(f"  Done.")
            sz_gb = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, files in os.walk(dzi_base + '_files')
                for f in files
            ) / 1024**3
            print(f"  Tile directory: {dzi_base}_files/  ({sz_gb:.2f} GB)")

    # ── Step 3: Write HTML viewer ────────────────────────────────────────────
    print(f"Writing HTML viewer → {html_file} ...")

    # Nav buttons HTML
    if nav_buttons:
        btn_lines = '\n'.join(
            f'        <input type="button" value="{label}" '
            f'onclick="goTo({x}, {y}, {zoom})" />'
            for label, x, y, zoom in nav_buttons
        )
        nav_html = NAV_BUTTON_HTML.format(buttons=btn_lines)
        goto_js = GOTO_JS.format(img_width=img.width, img_height=img.height)
    else:
        nav_html = ''
        goto_js = ''

    html = HTML_TEMPLATE.format(
        title=args.title,
        dzi_filename=f'{args.slug}.dzi',
        nav_html=nav_html,
        goto_js=goto_js,
    )

    if args.dry_run:
        print(f"  [DRY RUN] Would write {html_file}")
    else:
        with open(html_file, 'w') as f:
            f.write(html)
        print(f"  Done.")

    # ── Step 4: Update index.html ────────────────────────────────────────────
    print(f"Updating index.html ...")
    inject_into_index(index_file, city, args.slug, args.title, dry_run=args.dry_run)

    print()
    print(f"✓ Published: http://localhost/hires/{args.slug}-osd.html")


if __name__ == '__main__':
    main()
