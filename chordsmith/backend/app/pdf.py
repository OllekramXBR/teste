"""A PDF of the cifra, written by hand.

No dependency, for the same reason `midi.py` has none: the output is monospaced
text on a page, and every PDF library available would be several megabytes and a
build-time compiler to lay out something a fixed-width font already lays out.

Courier is one of the fourteen fonts every PDF reader is required to provide, so
nothing has to be embedded and the file stays a few kilobytes — which matters
when the thing is going onto a phone at a venue with no signal.

What this is *not* is a typesetter. It puts a monospaced chart on numbered
pages, and that is exactly what a cifra needs, because in a cifra the column a
chord sits in is the meaning.
"""

from __future__ import annotations

# A4 in points, and a monospaced grid that fits a 52-character cifra line with
# room for the longer chord rows above it.
PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 48
FONT_SIZE = 10
LINE_HEIGHT = 12.6
LINES_PER_PAGE = int((PAGE_HEIGHT - 2 * MARGIN) / LINE_HEIGHT)


def _escape(text: str) -> str:
    """Escape the three characters that mean something inside a PDF string."""
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _latin1(text: str) -> str:
    """Fold to what the standard Courier encoding can actually show.

    A cifra is full of Portuguese accents, which Latin-1 carries. The characters
    it cannot — the degree sign used for diminished chords is fine, but the
    musical symbols are not — are replaced rather than dropped, so a line never
    silently loses a chord.
    """
    replacements = {"°": "o", "♭": "b", "♯": "#", "–": "-", "—": "-", "’": "'", "“": '"', "”": '"'}
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.encode("latin-1", "replace").decode("latin-1")


def build_pdf(text: str, title: str = "") -> bytes:
    """Render plain monospaced text as a paginated PDF."""
    lines = [_latin1(line) for line in text.replace("\t", "    ").splitlines()]
    pages: list[list[str]] = [
        lines[start : start + LINES_PER_PAGE] for start in range(0, len(lines), LINES_PER_PAGE)
    ] or [[]]

    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)  # PDF object numbers are 1-based

    font = add(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"
    )

    # The page objects need the pages-tree number before it exists, and the tree
    # needs theirs. Reserving it first is the usual way out of that knot.
    tree_number = len(objects) + 1 + 2 * len(pages)

    page_numbers: list[int] = []
    for index, page in enumerate(pages):
        content = [b"BT", f"/F1 {FONT_SIZE} Tf".encode(), f"{LINE_HEIGHT} TL".encode()]
        content.append(f"1 0 0 1 {MARGIN} {PAGE_HEIGHT - MARGIN} Tm".encode())
        for line in page:
            content.append(f"({_escape(line)}) Tj".encode())
            content.append(b"T*")
        if len(pages) > 1:
            footer = f"{index + 1}/{len(pages)}"
            content.append(f"1 0 0 1 {PAGE_WIDTH - MARGIN - 30} {MARGIN / 2} Tm".encode())
            content.append(f"({footer}) Tj".encode())
        content.append(b"ET")

        stream = b"\n".join(content)
        stream_number = add(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
        page_numbers.append(
            add(
                f"<< /Type /Page /Parent {tree_number} 0 R "
                f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 {font} 0 R >> >> "
                f"/Contents {stream_number} 0 R >>".encode()
            )
        )

    kids = " ".join(f"{number} 0 R" for number in page_numbers)
    tree = add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_numbers)} >>".encode())
    assert tree == tree_number, "the reserved page-tree number did not match"

    catalog = add(f"<< /Type /Catalog /Pages {tree} 0 R >>".encode())
    info = add(f"<< /Title ({_escape(_latin1(title))}) /Producer (Metatron) >>".encode())

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    # The cross-reference table is what lets a reader jump to any object without
    # scanning the file, and it is the part a hand-written PDF usually gets
    # wrong: every offset is from the start of the file, in exactly 10 digits.
    start_xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\n"
        f"startxref\n{start_xref}\n%%EOF\n"
    ).encode()

    return bytes(out)
