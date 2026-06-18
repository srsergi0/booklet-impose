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