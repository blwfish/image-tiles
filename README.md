# image-tiles

Tools for stitching Sanborn fire insurance map JP2 sheets into composite images
and publishing them as DeepZoom tile sets for OpenSeadragon viewers.

## Tools

### `publish_map.py`
Converts a composite TIFF into a DeepZoom (DZI) tile tree and publishes it to
the nginx webserver directory, creating the HTML viewer and updating the index.

```bash
python3 publish_map.py <source.tif> <slug> <title> [options]

# Example:
python3 publish_map.py cities/roanoke-1951/composite.tif \
    Roanoke-1951 "Roanoke 1951" \
    --city Roanoke \
    --nav "Downtown Core:77000,62000,0.25;N&W Station:80000,64000,0.15"
```

Options:
- `--city CITY`     City name for grouping in index.html
- `--nav SPEC`      Nav buttons: `"Label:x,y,zoom;..."` (pixel coords, zoom ~0.1–0.5)
- `--webroot DIR`   Nginx webroot (default: `/Volumes/Files/claude/webserver`)
- `--tile-size N`   DZI tile size in pixels (default: 256)
- `--quality N`     JPEG tile quality (default: 85)
- `--dry-run`       Preview without writing

### `cities/<name>/stitch.py`
City-specific stitching script. Reads source JP2s, composites them at the
correct scale and position into a single pyramidal TIFF (`composite.tif`).

```bash
cd cities/roanoke-1951
python3 stitch.py              # full stitch → composite.tif
python3 stitch.py --dry-run    # preview canvas size and sheet positions
```

## City Data

Each city directory contains:
- `stitch.py` — compositing script with sheet positions
- `composite.tif` — assembled output (stored in Git LFS)
- `sources.txt` — LOC JP2 download URLs; re-fetch with `wget -i sources.txt`

| City | Year | Sheets | Canvas | Notes |
|------|------|--------|--------|-------|
| Roanoke VA | 1951 | 95 | 132,542 × 118,473 px | 50ft/in inner, 100ft/in outer ring |

## Workflow

1. Download JP2s: `wget -i cities/<name>/sources.txt -P cities/<name>/source/`
2. Stitch: `python3 cities/<name>/stitch.py`
3. Publish: `python3 publish_map.py cities/<name>/composite.tif <slug> "<title>" --city <city>`

## Requirements

- Python 3.9+
- [pyvips](https://libvips.github.io/pyvips/) (`pip install pyvips`)
- libvips 8.x (`brew install vips`)
