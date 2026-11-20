"""A tiny PDF writer: text, filled boxes and lines on US Letter pages, standard library only."""

from __future__ import annotations

# Helvetica advance widths (per 1000 units) for ASCII 32..126.
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
      556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
      1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
      667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
      333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
      556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
PAGE_W, PAGE_H = 612.0, 792.0


def text_width(text: str, size: float, bold: bool = False) -> float:
    total = 0
    for ch in text:
        code = ord(ch)
        total += _W[code - 32] if 32 <= code <= 126 else 556
    return total * size / 1000 * (1.05 if bold else 1.0)


def wrap(text: str, size: float, width: float, bold: bool = False) -> list[str]:
    """Greedy word wrap. Explicit newlines are kept; very long words are split."""
    lines: list[str] = []
    for paragraph in str(text).split("\n"):
        current = ""
        for word in paragraph.split():
            while text_width(word, size, bold) > width:
                cut = len(word)
                while cut > 1 and text_width(word[:cut], size, bold) > width:
                    cut -= 1
                if current:
                    lines.append(current)
                    current = ""
                lines.append(word[:cut])
                word = word[cut:]
            trial = f"{current} {word}".strip()
            if text_width(trial, size, bold) <= width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _esc(text: str) -> str:
    text = text.encode("cp1252", "replace").decode("cp1252")
    out = []
    for ch in text:
        if ch in "\\()":
            out.append("\\" + ch)
        elif ord(ch) > 126 or ord(ch) < 32:
            out.append("\\%03o" % ch.encode("cp1252", "replace")[0])
        else:
            out.append(ch)
    return "".join(out)


class Pdf:
    """Collects drawing operations per page and serialises a valid PDF 1.4 file."""

    def __init__(self, title: str = "Document"):
        self.title = title
        self.pages: list[list[str]] = [[]]

    def new_page(self) -> None:
        self.pages.append([])

    @property
    def _ops(self) -> list[str]:
        return self.pages[-1]

    def text(self, x: float, y: float, text: str, size: float = 10, bold: bool = False,
             color: tuple[float, float, float] = (0, 0, 0)) -> None:
        font = "F2" if bold else "F1"
        r, g, b = color
        self._ops.append(f"BT /{font} {size:g} Tf {r:g} {g:g} {b:g} rg {x:.2f} {y:.2f} Td ({_esc(text)}) Tj ET")

    def rect(self, x: float, y: float, w: float, h: float, fill: tuple[float, float, float] | None = None,
             stroke: tuple[float, float, float] | None = None, line: float = 0.6) -> None:
        parts = []
        if fill:
            parts.append(f"{fill[0]:g} {fill[1]:g} {fill[2]:g} rg")
        if stroke:
            parts.append(f"{stroke[0]:g} {stroke[1]:g} {stroke[2]:g} RG {line:g} w")
        op = "B" if fill and stroke else "f" if fill else "S"
        parts.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re {op}")
        self._ops.append(" ".join(parts))

    def hline(self, x1: float, x2: float, y: float, color=(0.7, 0.7, 0.7), line: float = 0.6) -> None:
        self._ops.append(f"{color[0]:g} {color[1]:g} {color[2]:g} RG {line:g} w {x1:.2f} {y:.2f} m {x2:.2f} {y:.2f} l S")

    def to_bytes(self) -> bytes:
        objects: list[bytes] = []

        def add(body: str | bytes) -> int:
            objects.append(body.encode("latin-1") if isinstance(body, str) else body)
            return len(objects)

        add("<< /Type /Catalog /Pages 2 0 R >>")
        add("")  # pages placeholder (object 2)
        add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        kids = []
        for ops in self.pages:
            stream = "\n".join(ops).encode("latin-1", "replace")
            content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
            page = add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:g} {PAGE_H:g}] "
                       f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content} 0 R >>")
            kids.append(f"{page} 0 R")
        objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode("latin-1")
        info = add(f"<< /Title ({_esc(self.title)}) /Producer (incident-report-form) >>")

        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info {info} 0 R >>\n"
                f"startxref\n{xref}\n%%EOF\n").encode()
        return bytes(out)
