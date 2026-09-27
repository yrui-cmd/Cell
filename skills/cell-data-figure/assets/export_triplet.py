"""Copy this function into the FINAL plot.py; never depend on the skill path.

Runtime dependencies: Matplotlib, Pillow. A single Figure produces all formats.
Export implementation follows Figure.savefig and Pillow TIFF/JPEG documentation:
https://matplotlib.org/stable/api/_as_gen/matplotlib.figure.Figure.savefig.html
https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html
This is a helper, not a figure design or statistical-analysis template.
"""
from pathlib import Path


def export_triplet(fig, output_stem, *, dpi=600, facecolor="white"):
    """Export one unchanged Matplotlib Figure as .tif, .jpg and vector .pdf.

    Set the figure size, font family and all layouts BEFORE calling this.
    Fixed full-canvas bounds preserve the same physical dimensions in all formats.
    Existing files with the same stem are replaced only after rendering succeeds.
    PDF keeps normal text/paths as vector objects; intentional image layers remain
    raster. Do not rasterize the entire figure or paste in a reference screenshot.
    """
    import io
    import math
    import os
    import tempfile

    import matplotlib as mpl
    from PIL import Image, features

    stem = Path(output_stem).expanduser()
    if not stem.name or stem.suffix:
        raise ValueError("output_stem must be a filename stem without an extension")
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi < 72:
        raise ValueError("dpi must be an integer >= 72; default is 600")
    width, height = [float(x) for x in fig.get_size_inches()]
    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError("Figure must have a finite positive physical size")
    if round(width * dpi) * round(height * dpi) > 150_000_000:
        raise ValueError("Raster export would exceed 150 million pixels; review size/dpi")
    stem.parent.mkdir(parents=True, exist_ok=True)
    paths = {ext: stem.with_suffix('.' + ext) for ext in ('tif', 'jpg', 'pdf')}
    for path in paths.values():
        if path.is_symlink():
            raise ValueError(f"Refusing to replace a symlink: {path}")

    # Resolve automatic layouts once, then freeze axes positions for all backends.
    fig.canvas.draw()
    if hasattr(fig, "get_layout_engine") and fig.get_layout_engine() is not None:
        fig.set_layout_engine('none')
    common = dict(dpi=dpi, bbox_inches=None, transparent=False,
                  facecolor=facecolor, edgecolor=facecolor)
    old_patch_color = fig.patch.get_facecolor()
    fig.patch.set_facecolor(facecolor)
    try:
        with tempfile.TemporaryDirectory(prefix='.figure-export-', dir=stem.parent) as td:
            temp = Path(td)
            # The PNG exists only in memory, never as a delivered preview file.
            with mpl.rc_context({'savefig.bbox': None, 'pdf.fonttype': 42,
                                 'pdf.use14corefonts': False,
                                 'savefig.transparent': False}):
                buf = io.BytesIO()
                fig.savefig(buf, format='png', **common)
                buf.seek(0)
                with Image.open(buf) as im:
                    rgb = im.convert('RGB')
                compression = 'tiff_lzw' if features.check('libtiff') else 'raw'
                rgb.save(temp / 'image.tif', format='TIFF', compression=compression,
                         dpi=(dpi, dpi))
                rgb.save(temp / 'image.jpg', format='JPEG', quality=95,
                         subsampling=0, optimize=True, dpi=(dpi, dpi))
                fig.savefig(temp / 'image.pdf', format='pdf',
                            metadata={'Creator': 'plot.py', 'CreationDate': None,
                                      'ModDate': None}, **common)
                rgb.close()
                buf.close()
            for ext, target in paths.items():
                os.replace(temp / ('image.' + ext), target)
    finally:
        fig.patch.set_facecolor(old_patch_color)
    return paths
