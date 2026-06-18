# booklet-impose

Generate booklet-format PDFs for duplex printing and folding.

Takes a PDF source document and imposes it into booklet layout — arranging pages so that when printed double-sided and folded, they appear in correct reading order.

## Features

- **Booklet imposition** — A5→A4, A4→A3, Letter, Legal
- **Auto-detect** source page size
- **Signatures** — group into booklets of N sheets for saddle stitching
- **Page range** — impose only selected pages
- **Batch mode** — combine multiple PDFs into one booklet
- **Gutter margin** — add spine area between pages
- **Crop marks** — for precise trimming
- **Sheet numbering** — bottom-center, bottom-left, etc.
- **Test printing** — extract a single sheet to verify alignment
- **HTML preview** — interactive visualization of page layout
- **De-imposition** — reverse the process, extract pages from a booklet
- **Verify** — show page order without generating a PDF

## Quick Start

```bash
pip install pymupdf
python3 booklet-impose.py document.pdf booklet.pdf
```

Then print:

```bash
lp -d <printer> -o media=A4 -o sides=two-sided-long-edge booklet.pdf
```

## Documentation

See [booklet-impose.md](booklet-impose.md) for full usage and options.

## License

MIT