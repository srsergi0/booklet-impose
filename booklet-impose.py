#!/usr/bin/env python3
"""
booklet-impose.py v2.0 — Generate booklet-format PDFs for duplex printing and folding.

USAGE:
    python3 booklet-impose.py input.pdf output.pdf [options]

SEE:
    python3 booklet-impose.py --help
"""

import argparse
import math
import sys
import os
import base64
import shutil
import subprocess
import tempfile

try:
    import pymupdf
except ImportError:
    print("Error: pymupdf is not installed.")
    print("Install with: pip install pymupdf")
    sys.exit(1)

VERSION = "2.0.0"

PAPER_SIZES = {
    "a4":     {"w": 595.28, "h": 841.89, "name": "A4 (210×297mm)"},
    "a3":     {"w": 841.89, "h": 1190.68, "name": "A3 (297×420mm)"},
    "letter":  {"w": 612.00, "h": 792.00, "name": "Letter (8.5×11in)"},
    "legal":   {"w": 612.00, "h": 1008.00, "name": "Legal (8.5×14in)"},
}

SOURCE_SIZES = {
    "a5":     {"w": 419.53, "h": 595.28, "name": "A5 (148×210mm)"},
    "a4":     {"w": 595.28, "h": 841.89, "name": "A4 (210×297mm)"},
    "letter":  {"w": 612.00, "h": 792.00, "name": "Letter (8.5×11in)"},
    "auto":   {"w": 0, "h": 0, "name": "Auto-detect"},
}

LANDSCAPE = {
    "a4":     {"w": 841.89, "h": 595.28},
    "a3":     {"w": 1190.68, "h": 841.89},
    "letter":  {"w": 792.00, "h": 612.00},
    "legal":   {"w": 1008.00, "h": 612.00},
}


def detect_source_size(src):
    page = src[0]
    w = page.rect.width
    h = page.rect.height
    tol = 5.0
    for name, size in SOURCE_SIZES.items():
        if name == "auto":
            continue
        if abs(w - size["w"]) < tol and abs(h - size["h"]) < tol:
            return name
        if abs(h - size["w"]) < tol and abs(w - size["h"]) < tol:
            return name + " (rotated)"
    return f"unknown ({w:.1f}×{h:.1f}pt)"


def create_blank_page(doc, width, height, label=True):
    page = doc.new_page(width=width, height=height)
    if label:
        page.insert_text(
            pymupdf.Point(width / 2 - 75, height / 2),
            "This page is intentionally blank",
            fontsize=14, color=(0.75, 0.75, 0.75), fontname="helv",
        )
    return page


def add_crop_marks(page, rect, margin=15):
    mark_len = 20
    c = (0.6, 0.6, 0.6)
    page.draw_line(pymupdf.Point(rect.x0 - margin, rect.y0), pymupdf.Point(rect.x0 - margin - mark_len, rect.y0), color=c, width=0.5)
    page.draw_line(pymupdf.Point(rect.x0, rect.y0 - margin), pymupdf.Point(rect.x0, rect.y0 - margin - mark_len), color=c, width=0.5)
    page.draw_line(pymupdf.Point(rect.x1 + margin, rect.y0), pymupdf.Point(rect.x1 + margin + mark_len, rect.y0), color=c, width=0.5)
    page.draw_line(pymupdf.Point(rect.x1, rect.y0 - margin), pymupdf.Point(rect.x1, rect.y0 - margin - mark_len), color=c, width=0.5)
    page.draw_line(pymupdf.Point(rect.x0 - margin, rect.y1), pymupdf.Point(rect.x0 - margin - mark_len, rect.y1), color=c, width=0.5)
    page.draw_line(pymupdf.Point(rect.x0, rect.y1 + margin), pymupdf.Point(rect.x0, rect.y1 + margin + mark_len), color=c, width=0.5)
    page.draw_line(pymupdf.Point(rect.x1 + margin, rect.y1), pymupdf.Point(rect.x1 + margin + mark_len, rect.y1), color=c, width=0.5)
    page.draw_line(pymupdf.Point(rect.x1, rect.y1 + margin), pymupdf.Point(rect.x1, rect.y1 + margin + mark_len), color=c, width=0.5)


def add_page_number(page, num, total, position="bottom-center"):
    if position == "none":
        return
    r = page.rect
    text = f"{num}"
    fontsize = 8
    color = (0.5, 0.5, 0.5)
    if position == "bottom-center":
        point = pymupdf.Point(r.width / 2 - 3, r.height - 15)
        page.insert_text(point, text, fontsize=fontsize, color=color, fontname="helv")
    elif position == "bottom-left":
        point = pymupdf.Point(15, r.height - 15)
        page.insert_text(point, text, fontsize=fontsize, color=color, fontname="helv")
    elif position == "bottom-right":
        point = pymupdf.Point(r.width - 25, r.height - 15)
        page.insert_text(point, text, fontsize=fontsize, color=color, fontname="helv")
    elif position == "top-center":
        point = pymupdf.Point(r.width / 2 - 3, 20)
        page.insert_text(point, text, fontsize=fontsize, color=color, fontname="helv")


def create_booklet(input_path, output_path, paper_size="a4", source_size="a5",
                   sigsize=0, blank_label=True, nopad=False,
                   gutter=0, crop_marks=False, numbering="none",
                   rotate_back=180, pages=None, quiet=False):
    if not quiet:
        print(f"  Reading: {input_path}")

    src = pymupdf.open(input_path)
    n_orig = src.page_count

    if pages:
        start, end = pages
        if start < 1 or end > n_orig or start > end:
            print(f"ERROR: Invalid page range: {start}-{end} (PDF has {n_orig} pages)")
            sys.exit(1)
        src_page_range = list(range(start - 1, end))
        n_orig = len(src_page_range)
        if not quiet:
            print(f"  Using pages {start}-{end} ({n_orig} pages)")
    else:
        src_page_range = list(range(n_orig))

    if not quiet:
        print(f"  Source pages: {n_orig}")

    if source_size == "auto":
        detected = detect_source_size(src)
        if not quiet:
            print(f"  Detected size: {detected}")
        if "a5" in detected:
            source_size = "a5"
        elif "a4" in detected:
            source_size = "a4"
        else:
            source_size = "a4"
            if not quiet:
                print(f"  Using {source_size} as fallback")

    src_size = SOURCE_SIZES.get(source_size, SOURCE_SIZES["a5"])
    land = LANDSCAPE.get(paper_size, LANDSCAPE["a4"])
    sheet_w = land["w"]
    sheet_h = land["h"]

    gutter_pt = gutter * 2.835

    n_pages = n_orig
    if nopad and n_pages % 4 != 0:
        print(f"ERROR: {n_orig} pages is not a multiple of 4. Remove --nopad to auto-pad.")
        sys.exit(1)
    while n_pages % 4 != 0:
        n_pages += 1

    padding = n_pages - n_orig
    if padding > 0 and not quiet:
        label_text = "with label" if blank_label else "unlabeled"
        print(f"  Adding {padding} blank page(s) ({label_text})")

    padded_src = pymupdf.open()
    for idx in src_page_range:
        padded_src.insert_pdf(src, from_page=idx, to_page=idx)
    for _ in range(padding):
        create_blank_page(padded_src, src_size["w"], src_size["h"], label=blank_label)

    n_sheets = n_pages // 4

    if not quiet:
        print(f"  Padded pages: {n_pages}")
        print(f"  {paper_size.upper()} sheets: {n_sheets}")
        if gutter > 0:
            print(f"  Gutter margin: {gutter}mm")

    if sigsize > 0:
        sheets_per_sig = sigsize
        total_sigs = math.ceil(n_sheets / sheets_per_sig)
        if not quiet:
            print(f"  Signatures: {total_sigs} of {sheets_per_sig} sheets each")
    else:
        sheets_per_sig = n_sheets
        total_sigs = 1

    half_w = (sheet_w - gutter_pt) / 2
    left_rect  = pymupdf.Rect(0, 0, half_w, sheet_h)
    right_rect = pymupdf.Rect(half_w + gutter_pt, 0, sheet_w, sheet_h)

    dst = pymupdf.open()

    dst.set_metadata({
        "title": os.path.splitext(os.path.basename(input_path))[0] + " (booklet)",
        "author": "booklet-impose.py",
        "subject": f"Booklet imposed - {n_pages} pages on {n_sheets} sheets",
        "creator": f"booklet-impose.py v{VERSION}",
    })

    sheet_count = 0
    for sig in range(total_sigs):
        sig_start = sig * sheets_per_sig
        sig_end = min(sig_start + sheets_per_sig, n_sheets)
        sig_n_sheets = sig_end - sig_start

        for i in range(sig_n_sheets):
            sheet = sig_start + i
            sheet_count += 1

            front_left  = n_pages - 2 * sheet
            front_right = 2 * sheet + 1
            back_left   = 2 * sheet + 2
            back_right  = n_pages - 2 * sheet - 1

            # --- FRONT ---
            front = dst.new_page(width=sheet_w, height=sheet_h)

            pidx = front_left - 1
            if 0 <= pidx < n_orig:
                front.show_pdf_page(left_rect, padded_src, pidx)

            pidx = front_right - 1
            if 0 <= pidx < n_orig:
                front.show_pdf_page(right_rect, padded_src, pidx)

            if crop_marks:
                add_crop_marks(front, left_rect)
                add_crop_marks(front, right_rect)

            if numbering != "none":
                add_page_number(front, sheet_count * 2 - 1, n_sheets * 2, numbering)

            # --- BACK ---
            back = dst.new_page(width=sheet_w, height=sheet_h)

            if rotate_back == 180:
                pidx = back_right - 1
                if 0 <= pidx < n_orig:
                    back.show_pdf_page(left_rect, padded_src, pidx, rotate=180)

                pidx = back_left - 1
                if 0 <= pidx < n_orig:
                    back.show_pdf_page(right_rect, padded_src, pidx, rotate=180)
            else:
                pidx = back_left - 1
                if 0 <= pidx < n_orig:
                    back.show_pdf_page(left_rect, padded_src, pidx)

                pidx = back_right - 1
                if 0 <= pidx < n_orig:
                    back.show_pdf_page(right_rect, padded_src, pidx)

            if crop_marks:
                add_crop_marks(back, left_rect)
                add_crop_marks(back, right_rect)

            if numbering != "none":
                add_page_number(back, sheet_count * 2, n_sheets * 2, numbering)

    dst.save(output_path)
    dst.close()
    padded_src.close()
    src.close()

    if not quiet:
        print(f"\n  ✓ PDF created: {output_path}")
        print(f"    Source pages: {n_orig}" + (f" (range: {pages[0]}-{pages[1]})" if pages else ""))
        print(f"    Padded pages: {n_pages}")
        print(f"    {paper_size.upper()} sheets: {n_sheets}")
        print(f"    Print: lp -d <printer> -o media={paper_size.upper()}" +
              (" -o sides=two-sided-long-edge" if rotate_back == 180 else " -o sides=two-sided-short-edge") +
              f" {output_path}")

    return n_sheets


def verify_booklet(input_path, paper_size="a4", pages=None, quiet=False):
    src = pymupdf.open(input_path)
    n_orig = src.page_count

    if pages:
        start, end = pages
        n_orig = end - start + 1

    n_pages = n_orig
    while n_pages % 4 != 0:
        n_pages += 1
    n_sheets = n_pages // 4
    padding = n_pages - n_orig

    print(f"  Source PDF: {input_path}")
    print(f"  Pages: {n_orig}" + (f" (+{padding} blank)" if padding > 0 else ""))
    print(f"  {paper_size.upper()} sheets: {n_sheets}")
    print(f"  Print: lp -d <printer> -o media={paper_size.upper()} -o sides=two-sided-long-edge")
    print()
    print(f"  {'Sheet':<6} {'Front L':<14} {'Front R':<14} {'Back L':<14} {'Back R':<14} {'Sig.':<6}")
    print(f"  {'─'*6} {'─'*14} {'─'*14} {'─'*14} {'─'*14} {'─'*6}")

    for sheet in range(n_sheets):
        front_left  = n_pages - 2 * sheet
        front_right = 2 * sheet + 1
        back_left   = 2 * sheet + 2
        back_right  = n_pages - 2 * sheet - 1

        fl = f"p.{front_left}" if front_left <= n_orig else "blank"
        fr = f"p.{front_right}" if front_right <= n_orig else "blank"
        bl = f"p.{back_right}" if back_right <= n_orig else "blank"
        br = f"p.{back_left}" if back_left <= n_orig else "blank"
        sig_num = (sheet // 4) + 1 if n_sheets > 4 else "-"

        print(f"  {sheet+1:<6} {fl:<14} {fr:<14} {bl:<14} {br:<14} {sig_num:<6}")

    src.close()


def _render_pages_external(input_path, page_indices, dpi, fmt, quiet):
    ext = "jpg" if fmt == "jpeg" else "png"
    tmpdir = tempfile.mkdtemp(prefix="booklet-preview-")
    try:
        pdftoppm = shutil.which("pdftoppm")
        mutool = shutil.which("mutool")
        first_page = page_indices[0] + 1
        last_page = page_indices[-1] + 1

        if pdftoppm:
            if not quiet:
                print(f"  Rendering with pdftoppm (poppler)...")
            prefix = os.path.join(tmpdir, "page")
            cmd = [pdftoppm, "-jpeg", "-r", str(dpi),
                   "-f", str(first_page), "-l", str(last_page),
                   input_path, prefix]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                if not quiet:
                    print(f"  pdftoppm failed: {result.stderr.strip()[:200]}")
                return None
            images = []
            first_w, first_h = 400, 566
            for i, idx in enumerate(page_indices):
                pn = idx + 1
                path = os.path.join(tmpdir, f"page-{pn:02d}.jpg")
                if not os.path.exists(path):
                    if not quiet:
                        print(f"  pdftoppm: missing {path}")
                    return None
                with open(path, "rb") as f:
                    img_data = f.read()
                mime = "image/jpeg"
                b64 = f"data:{mime};base64,{base64.b64encode(img_data).decode('ascii')}"
                w, h = _img_dims_from_jpeg(img_data)
                if i == 0:
                    first_w, first_h = w, h
                images.append(b64)
            if images:
                return images, first_w, first_h
            return None

        elif mutool:
            if not quiet:
                print(f"  Rendering with mutool (mupdf)...")
            images = []
            first_w, first_h = 400, 566
            for i, idx in enumerate(page_indices):
                pn = idx + 1
                outpath = os.path.join(tmpdir, f"page_{pn:04d}.{ext}")
                cmd = [mutool, "draw", "-r", str(dpi),
                       "-o", outpath, "-F", ext,
                       input_path, str(pn)]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    if not quiet and i == 0:
                        print(f"  mutool failed: {result.stderr.strip()}")
                    return None
                with open(outpath, "rb") as f:
                    img_data = f.read()
                mime = "image/jpeg" if fmt == "jpeg" else "image/png"
                b64 = f"data:{mime};base64,{base64.b64encode(img_data).decode('ascii')}"
                w, h = _img_dims(outpath, img_data)
                if i == 0:
                    first_w, first_h = w, h
                images.append(b64)
                if not quiet:
                    pct = (i + 1) / len(page_indices) * 100
                    print(f"    {i+1}/{len(page_indices)} ({pct:.0f}%)", end='\r')
            if not quiet:
                print(f"    {len(page_indices)}/{len(page_indices)} (100%)   ")
            return images, first_w, first_h

        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _img_dims_from_jpeg(data):
    w, h = 400, 566
    try:
        if data[:2] == b'\xff\xd8':
            i = 2
            while i < len(data) - 1:
                if data[i] != 0xFF:
                    break
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    h = (data[i + 5] << 8) | data[i + 6]
                    w = (data[i + 7] << 8) | data[i + 8]
                    return w, h
                elif marker == 0xD9:
                    break
                else:
                    length = (data[i + 2] << 8) | data[i + 3]
                    i += 2 + length
    except Exception:
        pass
    return w, h


def _img_dims(path_or_none, img_data):
    w, h = 400, 566
    try:
        if path_or_none and os.path.exists(path_or_none):
            import struct
            with open(path_or_none, "rb") as f:
                header = f.read(24)
            if header[:8] == b'\x89PNG\r\n\x1a\n':
                w = struct.unpack(">I", header[16:20])[0]
                h = struct.unpack(">I", header[20:24])[0]
            elif header[:2] == b'\xff\xd8':
                pass
    except Exception:
        pass
    return w, h


def _render_pages_pymupdf(input_path, page_indices, dpi, fmt, quiet):
    src = pymupdf.open(input_path)
    images = []
    first_w, first_h = 400, 566
    for i, idx in enumerate(page_indices):
        page = src[idx]
        pix = page.get_pixmap(dpi=dpi)
        if fmt == "jpeg":
            img_bytes = pix.tobytes("jpeg")
            mime = "image/jpeg"
            img_b64 = base64.b64encode(img_bytes).decode('ascii')
        else:
            img_bytes = pix.tobytes("png")
            mime = "image/png"
            img_b64 = base64.b64encode(img_bytes).decode('ascii')
        b64_uri = f"data:{mime};base64,{img_b64}"
        if i == 0:
            first_w, first_h = pix.width, pix.height
        images.append(b64_uri)
        if not quiet:
            pct = (i + 1) / len(page_indices) * 100
            print(f"    {i+1}/{len(page_indices)} ({pct:.0f}%)", end='\r')
    if not quiet:
        print(f"    {len(page_indices)}/{len(page_indices)} (100%)   ")
    src.close()
    return images, first_w, first_h


def generate_preview(input_path, paper_size="a4", source_size="a5", pages=None, quiet=False):
    src = pymupdf.open(input_path)

    if pages:
        start, end = pages
        page_indices = list(range(start - 1, min(end, src.page_count)))
    else:
        start = 1
        end = src.page_count
        page_indices = list(range(src.page_count))

    n_orig = len(page_indices)
    src.close()

    n_pages = n_orig
    while n_pages % 4 != 0:
        n_pages += 1
    n_sheets = n_pages // 4

    if not quiet:
        print(f"  Rendering {n_orig} pages to images...")

    render_methods = [
        ("pdftoppm", lambda: _render_pages_external(input_path, page_indices, 72, "jpeg", quiet)),
        ("mutool", lambda: _render_pages_external(input_path, page_indices, 72, "jpeg", quiet)),
    ]

    page_images = None
    page_w, page_h = 400, 566
    used_method = None

    for name, func in render_methods:
        result = func()
        if result is not None:
            page_images, page_w, page_h = result
            used_method = name
            break

    if page_images is None:
        if not quiet:
            print(f"  No external renderer found, using pymupdf (install poppler for faster rendering)...")
        page_images, page_w, page_h = _render_pages_pymupdf(input_path, page_indices, 72, "jpeg", quiet)
        used_method = "pymupdf"

    if not quiet:
        print(f"  Rendered {len(page_images)} pages via {used_method}")

    html_path = os.path.splitext(input_path)[0] + "-preview.html"

    sheet_rows = []
    for sheet in range(n_sheets):
        fl = n_pages - 2 * sheet
        fr = 2 * sheet + 1
        bl = 2 * sheet + 2
        br = n_pages - 2 * sheet - 1
        def pn(p):
            return f'<span class="pn">{p}</span>' if p <= n_orig else '<span class="pn blank">&#8709;</span>'
        sheet_rows.append(f'''<div class="sheet-row">
  <div class="sheet-num">{sheet+1}</div>
  <div class="side front">
    <div class="side-label">FRONT</div>
    <div class="half left">{pn(fl)}</div>
    <div class="half right">{pn(fr)}</div>
  </div>
  <div class="side back">
    <div class="side-label">BACK &#x27F2;</div>
    <div class="half left">{pn(br)}</div>
    <div class="half right">{pn(bl)}</div>
  </div>
</div>''')

    pages_js = '[\n' + ',\n'.join(f'  "{img}"' for img in page_images) + '\n]'

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Booklet Preview &mdash; {os.path.basename(input_path)}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; background: #1a1a2e; color: #eee; }}
.header {{ background: #16213e; padding: 12px 20px; display: flex; align-items: center; gap: 16px; border-bottom: 2px solid #0f3460; }}
.header h1 {{ font-size: 18px; font-weight: 600; color: #e94560; }}
.header .info {{ font-size: 13px; color: #888; }}
.tabs {{ display: flex; gap: 0; }}
.tab {{ padding: 8px 20px; cursor: pointer; font-size: 13px; font-weight: 500; background: #16213e; color: #888; border: 1px solid #0f3460; border-bottom: none; border-radius: 8px 8px 0 0; transition: all 0.2s; }}
.tab.active {{ background: #1a1a2e; color: #e94560; border-color: #e94560; }}
.tab:hover:not(.active) {{ color: #ccc; }}
.content {{ display: none; }}
.content.active {{ display: block; }}

/* Flipbook view */
#flipbook-view {{ min-height: calc(100vh - 100px); display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px; }}
#flipbook-container {{ width: 100%; max-width: 900px; }}
.stf__parent {{ margin: 0 auto; }}
.page-wrapper {{ perspective: 2000px; }}
.flipbook-nav {{ display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 16px; }}
.flipbook-nav button {{ background: #0f3460; color: #fff; border: none; padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; transition: background 0.2s; }}
.flipbook-nav button:hover {{ background: #e94560; }}
.flipbook-nav button:disabled {{ background: #333; color: #666; cursor: default; }}
.flipbook-nav .page-info {{ font-size: 14px; color: #888; min-width: 100px; text-align: center; }}
.loading {{ color: #888; font-size: 16px; text-align: center; padding: 40px; }}

/* Fallback viewer (if StPageFlip fails) */
#fallback-viewer {{ display: none; text-align: center; padding: 20px; }}
#fallback-viewer .page-display {{ max-height: 75vh; display: flex; align-items: center; justify-content: center; }}
#fallback-viewer .page-display img {{ max-height: 75vh; max-width: 90vw; box-shadow: 0 4px 24px rgba(0,0,0,0.5); border-radius: 4px; }}
#fallback-viewer .spread-display {{ display: flex; gap: 4px; justify-content: center; align-items: center; }}
#fallback-viewer .spread-display img {{ max-height: 70vh; max-width: 45vw; box-shadow: 0 4px 24px rgba(0,0,0,0.5); border-radius: 4px; }}

/* Print layout view */
#print-view {{ padding: 16px 20px; }}
.sheet-row {{ display: flex; align-items: stretch; margin-bottom: 6px; gap: 6px; }}
.sheet-num {{ width: 40px; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 700; color: #e94560; flex-shrink: 0; }}
.side {{ flex: 1; display: flex; border: 2px solid #333; border-radius: 6px; overflow: hidden; min-height: 48px; }}
.side.front {{ background: #1e2a3a; }}
.side.back {{ background: #2a1e2e; }}
.side-label {{ font-size: 10px; padding: 2px 8px; background: rgba(255,255,255,0.1); color: #666; writing-mode: vertical-lr; display: flex; align-items: center; }}
.half {{ flex: 1; display: flex; align-items: center; justify-content: center; padding: 8px 4px; border: 1px dashed #333; min-height: 48px; }}
.pn {{ font-size: 18px; font-weight: 700; color: #ccc; }}
.pn.blank {{ color: #444; }}
.print-info {{ margin-top: 20px; padding: 12px 16px; background: #16213e; border-radius: 8px; border: 1px solid #0f3460; }}
.print-info code {{ background: #0f3460; padding: 2px 6px; border-radius: 3px; color: #e94560; font-size: 13px; }}
.print-info p {{ margin: 4px 0; font-size: 13px; color: #aaa; }}
</style>
</head>
<body>

<div class="header">
  <h1>&#x1F4D6; Booklet Preview</h1>
  <div class="info">{os.path.basename(input_path)} &bull; {n_orig} pages &bull; {n_sheets} {paper_size.upper()} sheets</div>
  <div style="flex:1"></div>
  <div class="tabs">
    <div class="tab active" onclick="switchTab('flipbook')">&#x1F4DA; Flipbook</div>
    <div class="tab" onclick="switchTab('print')">&#x1F5A8; Print Layout</div>
  </div>
</div>

<div id="flipbook-view" class="content active">
  <div id="loading" class="loading">Loading flipbook...</div>
  <div id="flipbook-container" style="display:none;">
    <div id="flipbook"></div>
  </div>
  <div class="flipbook-nav" id="flipbook-nav" style="display:none;">
    <button id="btn-prev" onclick="flipPrev()">&#x25C0; Prev</button>
    <span class="page-info" id="page-info">Page 1</span>
    <button id="btn-next" onclick="flipNext()">Next &#x25B6;</button>
  </div>
  <div id="fallback-viewer">
    <div id="fallback-display"></div>
  </div>
</div>

<div id="print-view" class="content">
  {''.join(sheet_rows)}
  <div class="print-info">
    <p><strong>Pages:</strong> {n_orig} (+{n_pages - n_orig} blank) &bull; <strong>Sheets:</strong> {n_sheets}</p>
    <p><strong>Print command:</strong> <code>lp -d PRINTER -o media={paper_size.upper()} -o sides=two-sided-long-edge booklet.pdf</code></p>
    <p><strong>Imposition order:</strong> Front L = N&minus;2i | Front R = 2i+1 | Back L (rotated 180&deg;) = N&minus;2i&minus;1 | Back R (rotated 180&deg;) = 2i+2</p>
  </div>
</div>

<script>
const PAGE_IMAGES = {pages_js};
const TOTAL_PAGES = {n_orig};
const TOTAL_SHEETS = {n_sheets};
const PAGE_W = {page_w};
const PAGE_H = {page_h};

let pageFlip = null;
let useFallback = false;

function switchTab(name) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.content').forEach(c => c.classList.remove('active'));
  if (name === 'flipbook') {{
    document.querySelector('.tab:first-child').classList.add('active');
    document.getElementById('flipbook-view').classList.add('active');
  }} else {{
    document.querySelector('.tab:last-child').classList.add('active');
    document.getElementById('print-view').classList.add('active');
  }}
}}

function initFlipbook() {{
  const container = document.getElementById('flipbook');
  const containerW = Math.min(window.innerWidth - 40, 900);
  const containerH = window.innerHeight - 160;
  const pageRatio = PAGE_W / PAGE_H;
  const displayH = Math.min(containerH, 700);
  const displayW = displayH * pageRatio;

  try {{
    const StPageFlip = window.St;
    if (!StPageFlip || !StPageFlip.PageFlip) throw new Error('StPageFlip not loaded');

    const pages = PAGE_IMAGES.map((src, i) => {{
      const div = document.createElement('div');
      div.className = 'page-wrapper';
      div.style.width = displayW + 'px';
      div.style.height = displayH + 'px';
      div.setAttribute('data-density', i === 0 || i === TOTAL_PAGES - 1 ? 'hard' : 'soft');
      const img = document.createElement('img');
      img.src = src;
      img.style.width = '100%';
      img.style.height = '100%';
      img.style.objectFit = 'contain';
      img.alt = 'Page ' + (i + 1);
      div.appendChild(img);
      const label = document.createElement('div');
      label.style.cssText = 'position:absolute;bottom:6px;right:10px;font-size:11px;color:rgba(0,0,0,0.35);';
      label.textContent = i + 1;
      div.appendChild(label);
      return div;
    }});

    container.style.width = displayW + 'px';
    container.style.height = displayH + 'px';
    pages.forEach(p => container.appendChild(p));

    pageFlip = new StPageFlip.PageFlip(container, {{
      width: displayW,
      height: displayH,
      size: 'stretch',
      minWidth: 280,
      maxWidth: displayW * 1.5,
      minHeight: 400,
      maxHeight: displayH * 1.5,
      showCover: true,
      maxShadowOpacity: 0.5,
      mobileScrollSupport: true,
      clickEventForward: false,
      useMouseEvents: true,
      swipeDistance: 30,
      showPageCorners: true,
      disableFlipByClick: false,
      flippingTime: 700,
      usePortrait: true,
      startZIndex: 0,
      autoSize: true,
      drawShadow: true,
    }});

    pageFlip.loadFromHTML(pages);
    pageFlip.on('flip', (e) => updateNav());
    pageFlip.on('changeOrientation', (e) => updateNav());

    document.getElementById('loading').style.display = 'none';
    document.getElementById('flipbook-container').style.display = 'block';
    document.getElementById('flipbook-nav').style.display = 'flex';
    updateNav();

  }} catch (e) {{
    console.warn('StPageFlip unavailable, using fallback viewer:', e);
    useFallback = true;
    initFallback();
  }}
}}

function initFallback() {{
  document.getElementById('loading').style.display = 'none';
  document.getElementById('flipbook-container').style.display = 'none';
  document.getElementById('flipbook-nav').style.display = 'flex';
  const fb = document.getElementById('fallback-viewer');
  fb.style.display = 'block';

  let currentSpread = 0;
  const totalSpreads = Math.ceil(TOTAL_PAGES / 2);

  function showSpread() {{
    const display = document.getElementById('fallback-display');
    display.innerHTML = '';
    display.className = 'spread-display';
    const leftIdx = currentSpread * 2;
    const rightIdx = currentSpread * 2 + 1;
    const leftImg = document.createElement('img');
    leftImg.src = PAGE_IMAGES[leftIdx];
    leftImg.alt = 'Page ' + (leftIdx + 1);
    display.appendChild(leftImg);
    if (rightIdx < TOTAL_PAGES) {{
      const rightImg = document.createElement('img');
      rightImg.src = PAGE_IMAGES[rightIdx];
      rightImg.alt = 'Page ' + (rightIdx + 1);
      display.appendChild(rightImg);
    }}
    updateFallbackNav();
  }}

  function updateFallbackNav() {{
    const leftPage = currentSpread * 2 + 1;
    const rightPage = Math.min(currentSpread * 2 + 2, TOTAL_PAGES);
    document.getElementById('page-info').textContent = leftPage + '-' + rightPage + ' / ' + TOTAL_PAGES;
    document.getElementById('btn-prev').disabled = currentSpread === 0;
    document.getElementById('btn-next').disabled = currentSpread >= totalSpreads - 1;
  }}

  window.flipPrev = () => {{ if (currentSpread > 0) {{ currentSpread--; showSpread(); }} }};
  window.flipNext = () => {{ if (currentSpread < totalSpreads - 1) {{ currentSpread++; showSpread(); }} }};

  showSpread();
}}

function updateNav() {{
  if (!pageFlip) return;
  const current = pageFlip.getPageIndex();
  const leftPage = (current + 1);
  const rightPage = Math.min(current + 2, TOTAL_PAGES);
  document.getElementById('page-info').textContent = leftPage + '-' + rightPage + ' / ' + TOTAL_PAGES;
  document.getElementById('btn-prev').disabled = current <= 0;
  document.getElementById('btn-next').disabled = current >= TOTAL_PAGES - 2;
}}

function flipPrev() {{
  if (useFallback) return;
  if (pageFlip) pageFlip.flipPrev();
}}

function flipNext() {{
  if (useFallback) return;
  if (pageFlip) pageFlip.flipNext();
}}

document.addEventListener('keydown', (e) => {{
  if (e.key === 'ArrowLeft') {{ flipPrev(); e.preventDefault(); }}
  if (e.key === 'ArrowRight') {{ flipNext(); e.preventDefault(); }}
}});

const scripts = [
  'https://cdn.jsdelivr.net/npm/page-flip@2.0.7/dist/js/page-flip.browser.js'
];
let loaded = 0;
scripts.forEach(url => {{
  const s = document.createElement('script');
  s.src = url;
  s.onload = () => {{ loaded++; if (loaded === scripts.length) initFlipbook(); }};
  s.onerror = () => {{ loaded++; if (loaded === scripts.length) initFlipbook(); }};
  document.head.appendChild(s);
}});
if (scripts.length === 0) initFlipbook();
</script>
</body>
</html>'''

    with open(html_path, "w") as f:
        f.write(html)

    if not quiet:
        size_mb = os.path.getsize(html_path) / (1024 * 1024)
        print(f"  Preview: {html_path}")
        print(f"  Size: {size_mb:.1f} MB")
        print(f"  Open: open {html_path}")

    return html_path


def deimpose_booklet(input_path, output_path, quiet=False):
    src = pymupdf.open(input_path)
    total = src.page_count
    n_sheets = total // 2

    if total % 2 != 0:
        print(f"ERROR: PDF has {total} pages (odd number). A valid booklet has even pages.")
        src.close()
        sys.exit(1)

    land = LANDSCAPE.get("a4", LANDSCAPE["a4"])

    pages_extracted = {}
    for sheet_idx in range(n_sheets):
        front_idx = sheet_idx * 2
        back_idx = sheet_idx * 2 + 1

        front_page = src[front_idx]
        back_page = src[back_idx]

        front_left_num = 2 * n_sheets - 2 * sheet_idx
        front_right_num = 2 * sheet_idx + 1
        back_right_num = 2 * n_sheets - 2 * sheet_idx - 1
        back_left_num = 2 * sheet_idx + 2

        pages_extracted[front_left_num] = (front_idx, "left", False)
        pages_extracted[front_right_num] = (front_idx, "right", False)
        pages_extracted[back_left_num] = (back_idx, "right", True)
        pages_extracted[back_right_num] = (back_idx, "left", True)

    max_page = max(pages_extracted.keys())
    actual_total = min(max_page, n_sheets * 4)

    out = pymupdf.open()
    for p in range(1, actual_total + 1):
        if p not in pages_extracted:
            continue
        src_idx, side, rotated = pages_extracted[p]
        src_page = src[src_idx]

        page_w = src_page.rect.width / 2 - 2
        page_h = src_page.rect.height - 4

        new_page = out.new_page(width=page_w, height=page_h)
        clip = pymupdf.Rect(0, 0, page_w, page_h)

        if side == "right":
            clip = pymupdf.Rect(src_page.rect.width / 2, 0, src_page.rect.width, page_h)

        new_page.show_pdf_page(clip, src[:], src_idx, rotate=180 if rotated else 0)

    out.save(output_path)
    out.close()
    src.close()

    if not quiet:
        print(f"  ✓ De-imposed PDF: {output_path}")
        print(f"    Extracted pages: {len(pages_extracted)}")


def main():
    parser = argparse.ArgumentParser(
        prog="booklet-impose",
        description="""
╔═══════════════════════════════════════════════════════════╗
║              booklet-impose.py v""" + VERSION + """                        ║
║     Generate booklet PDFs for duplex printing & folding    ║
╚═══════════════════════════════════════════════════════════╝""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  # Standard booklet
  %(prog)s document.pdf booklet.pdf

  # Verify page order without generating PDF
  %(prog)s document.pdf --verify

  # Extract just sheet 3 for test printing
  %(prog)s document.pdf -t 3

  # Signatures of 4 sheets (for saddle stitching)
  %(prog)s document.pdf booklet.pdf --sigsize 4

  # Pages 5-20 only
  %(prog)s document.pdf booklet.pdf --pages 5-20

  # With gutter margin and crop marks
  %(prog)s document.pdf booklet.pdf --gutter 5 --crop-marks

  # Generate HTML preview
  %(prog)s document.pdf --preview

  # De-impose a booklet
  %(prog)s booklet.pdf restored.pdf --deimpose

  # Combine multiple PDFs into a booklet
  %(prog)s ch1.pdf ch2.pdf ch3.pdf booklet.pdf --batch

PRINTING:
  lp -d <printer> -o media=A4 -o sides=two-sided-long-edge booklet.pdf
  # If the back side prints inverted, use --rotate-back none:
  %(prog)s document.pdf booklet.pdf --rotate-back none
        """)

    parser.add_argument("input", nargs="+", help="Source PDF(s)")
    parser.add_argument("output", nargs="?", default=None, help="Output PDF")

    struct_group = parser.add_argument_group("Booklet structure")
    struct_group.add_argument("--size", choices=list(PAPER_SIZES.keys()), default="a4",
                             help="Target paper size (default: a4)")
    struct_group.add_argument("--source", choices=list(SOURCE_SIZES.keys()), default="a5",
                             help="Source PDF page size (default: a5, 'auto' to detect)")
    struct_group.add_argument("--sigsize", type=int, default=0,
                             help="Signatures of N sheets for saddle stitching (default: 0=single)")
    struct_group.add_argument("--pages", type=str, default=None, metavar="START-END",
                             help="Page range, e.g. 5-20")
    struct_group.add_argument("--batch", action="store_true",
                             help="Combine multiple PDFs into one booklet")

    print_group = parser.add_argument_group("Print settings")
    print_group.add_argument("--rotate-back", choices=["180", "none"], default="180",
                            help="Back side rotation: '180' for long-edge duplex (default), 'none' if printer handles it")
    print_group.add_argument("--gutter", type=float, default=0, metavar="MM",
                            help="Gutter margin between pages in mm (default: 0)")
    print_group.add_argument("--crop-marks", action="store_true",
                            help="Add crop marks")
    print_group.add_argument("--numbering", choices=["none", "bottom-center", "bottom-left", "bottom-right", "top-center"],
                            default="none", help="Add sheet numbers (default: none)")

    pad_group = parser.add_argument_group("Blank pages")
    pad_group.add_argument("--nopad", action="store_true",
                          help="Error if page count is not a multiple of 4 (no padding)")
    pad_group.add_argument("--blank-label", action="store_true", default=True,
                          help="Label blank padding pages (default)")
    pad_group.add_argument("--no-blank-label", action="store_false", dest="blank_label",
                          help="Leave blank pages empty")

    check_group = parser.add_argument_group("Verification & testing")
    check_group.add_argument("--verify", "-v", action="store_true",
                            help="Show page order without generating PDF")
    check_group.add_argument("--test", "-t", type=int, default=None, metavar="N",
                            help="Extract only sheet N for test printing")
    check_group.add_argument("--preview", "-p", action="store_true",
                            help="Generate interactive HTML preview")

    other_group = parser.add_argument_group("Other options")
    other_group.add_argument("--deimpose", "-d", action="store_true",
                           help="Reverse: extract pages in order from a booklet")
    other_group.add_argument("--quiet", "-q", action="store_true",
                           help="Quiet mode: errors only")
    other_group.add_argument("--metadata", type=str, default=None, metavar="TITLE",
                           help="PDF title (metadata)")
    other_group.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    args = parser.parse_args()

    pages = None
    if args.pages:
        try:
            start, end = map(int, args.pages.split("-"))
            pages = (start, end)
        except ValueError:
            parser.error("--pages requires START-END format, e.g. --pages 5-20")

    if args.verify:
        verify_booklet(args.input[0], args.size, pages, args.quiet)
        return

    if args.preview:
        generate_preview(args.input[0], args.size, args.source, pages)
        return

    if args.deimpose:
        if not args.output:
            args.output = os.path.splitext(args.input[0])[0] + "-deimposed.pdf"
        deimpose_booklet(args.input[0], args.output, args.quiet)
        return

    if not args.output:
        if args.test:
            args.output = os.path.splitext(args.input[0])[0] + f"-sheet{args.test}.pdf"
        else:
            args.output = os.path.splitext(args.input[0])[0] + "-booklet.pdf"

    if args.batch and len(args.input) > 1:
        if not args.quiet:
            print(f"  Combining {len(args.input)} PDFs...")
        combined = pymupdf.open()
        for f in args.input:
            if not args.quiet:
                print(f"    + {os.path.basename(f)}")
            combined.insert_pdf(pymupdf.open(f))
        temp_path = "/tmp/booklet-combined.pdf"
        combined.save(temp_path)
        combined.close()
        input_path = temp_path
    else:
        input_path = args.input[0]

    rotate_back = 180 if args.rotate_back == "180" else 0

    n_sheets = create_booklet(
        input_path, args.output,
        paper_size=args.size,
        source_size=args.source,
        sigsize=args.sigsize,
        blank_label=args.blank_label,
        nopad=args.nopad,
        gutter=args.gutter,
        crop_marks=args.crop_marks,
        numbering=args.numbering,
        rotate_back=rotate_back,
        pages=pages,
        quiet=args.quiet,
    )

    if args.metadata:
        doc = pymupdf.open(args.output)
        doc.set_metadata({"title": args.metadata, "author": "booklet-impose.py", "creator": f"booklet-impose.py v{VERSION}"})
        doc.save(args.output, incremental=True)
        doc.close()

    if args.test:
        if args.test < 1 or args.test > n_sheets:
            print(f"ERROR: Sheet {args.test} does not exist. Booklet has {n_sheets} sheets (1-{n_sheets}).")
            sys.exit(1)

        booklet = pymupdf.open(args.output)
        total = booklet.page_count

        idx_front = (args.test - 1) * 2
        idx_back = (args.test - 1) * 2 + 1

        test_path = os.path.splitext(args.input[0])[0] + f"-sheet{args.test}.pdf"
        test_dst = pymupdf.open()
        test_dst.insert_pdf(booklet, from_page=idx_front, to_page=min(idx_back, total - 1))
        test_dst.save(test_path)
        test_dst.close()
        booklet.close()

        if not args.quiet:
            print(f"\n  ✓ Sheet {args.test} extracted to: {test_path}")
            print(f"  Print: lp -d <printer> -o media={args.size.upper()} -o sides=two-sided-long-edge {test_path}")


if __name__ == "__main__":
    main()