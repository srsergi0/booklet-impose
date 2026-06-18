# booklet-impose.py

Generate booklet-format PDFs for duplex printing on A4 (or other sizes) and folding in half.

## Installation

```bash
pip install pymupdf
```

## Basic Usage

```bash
# Standard booklet (A5 → A4 booklet)
python3 booklet-impose.py document.pdf booklet.pdf

# Verify page order without generating a file
python3 booklet-impose.py document.pdf --verify

# Print just sheet 3 for testing
python3 booklet-impose.py document.pdf --test 3

# Signatures of 4 sheets (for saddle stitching)
python3 booklet-impose.py document.pdf booklet.pdf --sigsize 4

# A4 source (for larger booklets on A3)
python3 booklet-impose.py document.pdf booklet.pdf --source a4 --size a3

# No label on blank padding pages
python3 booklet-impose.py document.pdf booklet.pdf --no-blank-label

# Print the result
lp -d <printer> -o media=A4 -o sides=two-sided-long-edge booklet.pdf
```

## Options

| Option | Description |
|--------|-------------|
| `--size a4/a3/letter/legal` | Target paper size (default: a4) |
| `--source a5/a4/letter/auto` | Source PDF page size (default: a5) |
| `--sigsize N` | Group into signatures of N sheets (for saddle stitching) |
| `--test N` | Extract only sheet N for test printing |
| `--verify` | Show page order for each sheet without generating PDF |
| `--preview` | Generate interactive HTML preview |
| `--pages START-END` | Use only pages in the given range |
| `--batch` | Combine multiple PDFs into one booklet |
| `--rotate-back 180/none` | Back side rotation: 180 for long-edge duplex (default), none if printer handles it |
| `--gutter MM` | Gutter margin between pages in mm (default: 0) |
| `--crop-marks` | Add crop marks |
| `--numbering POSITION` | Add sheet numbers (none, bottom-center, bottom-left, bottom-right, top-center) |
| `--deimpose` | Reverse: extract pages in order from a booklet |
| `--nopad` | Error if page count is not a multiple of 4 |
| `--blank-label` | Label blank padding pages (default) |
| `--no-blank-label` | Leave blank pages empty |
| `--metadata TITLE` | Set PDF title metadata |
| `--quiet` | Quiet mode: errors only |

## How It Works

1. Takes a PDF of A5 pages (or A4 with `--source a4`)
2. Pads with blank pages up to a multiple of 4 if needed
3. Imposes pages onto landscape A4 sheets:
   - **Front**: page N-2i (left) | page 2i+1 (right)
   - **Back**: rotated 180° with left/right swapped
4. When printed duplex (long-edge) and folded, pages appear in correct order

## Verification Example

```
$ python3 booklet-impose.py document.pdf --verify

  Pages: 44
  A4 sheets: 11

  Sheet  Front L       Front R       Back L        Back R        Sig.
  ────── ────────────── ────────────── ────────────── ────────────── ──────
  1      p.44           p.1            p.43           p.2            -
  2      p.42           p.3            p.41           p.4            -
  3      p.40           p.5            p.39           p.6            -
  ...
  11     p.24           p.21           p.23           p.22           -
```

## De-imposition

Reverse the booklet process to extract individual pages:

```bash
python3 booklet-impose.py booklet.pdf restored.pdf --deimpose
```

## HTML Preview

Generate an interactive HTML visualization of the booklet layout:

```bash
python3 booklet-impose.py document.pdf --preview
```