"""Two drawing backends that share the ERD painter in erd.py."""
from __future__ import annotations

from html import escape
from typing import Optional

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
from reportlab.lib.colors import HexColor

from .erd import Layout, draw_erd


# ---------------------------------------------------------------- SVG
class SvgCanvas:
    def __init__(self):
        self.parts: list[str] = []

    def rect(self, x, y, w, h, fill=None, stroke=None, radius=0, stroke_width=1):
        self.parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{radius}" '
            f'fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{stroke_width}"/>'
        )

    def line(self, x1, y1, x2, y2, stroke, width=1):
        self.parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{width}"/>'
        )

    def polyline(self, points, stroke, width=1):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        self.parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="{width}" '
            f'stroke-linejoin="round"/>'
        )

    def circle(self, cx, cy, r, fill, stroke, width=1):
        self.parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{width}"/>'
        )

    def text(self, x, y, s, size, color, bold=False, anchor="start", link: Optional[str] = None):
        weight = ' font-weight="bold"' if bold else ""
        node = (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}"'
                f'{weight} text-anchor="{anchor}">{escape(s)}</text>')
        if link:
            node = f'<a href="{escape(link)}">{node}</a>'
        self.parts.append(node)


def erd_svg(lay: Layout, link_tables: bool = False) -> str:
    cv = SvgCanvas()
    draw_erd(cv, lay, link_tables=link_tables)
    body = "\n".join(cv.parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lay.width:.0f} {lay.height:.0f}" '
        f'width="{lay.width:.0f}" height="{lay.height:.0f}" '
        f'font-family="Helvetica, Arial, sans-serif" role="img" '
        f'aria-label="Entity relationship diagram">\n{body}\n</svg>'
    )


# ---------------------------------------------------------------- ReportLab
class RLCanvas:
    """Draws into a ReportLab Drawing, flipping y so layouts stay top-left based."""

    def __init__(self, height: float, drawing: Drawing):
        self.h = height
        self.d = drawing

    def _c(self, value):
        return HexColor(value) if value else None

    def rect(self, x, y, w, h, fill=None, stroke=None, radius=0, stroke_width=1):
        self.d.add(Rect(x, self.h - y - h, w, h, rx=radius, ry=radius,
                        fillColor=self._c(fill), strokeColor=self._c(stroke),
                        strokeWidth=stroke_width if stroke else 0))

    def line(self, x1, y1, x2, y2, stroke, width=1):
        self.d.add(Line(x1, self.h - y1, x2, self.h - y2,
                        strokeColor=self._c(stroke), strokeWidth=width))

    def polyline(self, points, stroke, width=1):
        flat = []
        for x, y in points:
            flat += [x, self.h - y]
        self.d.add(PolyLine(flat, strokeColor=self._c(stroke), strokeWidth=width,
                            strokeLineJoin=1))

    def circle(self, cx, cy, r, fill, stroke, width=1):
        self.d.add(Circle(cx, self.h - cy, r, fillColor=self._c(fill),
                          strokeColor=self._c(stroke), strokeWidth=width))

    def text(self, x, y, s, size, color, bold=False, anchor="start", link=None):
        self.d.add(String(x, self.h - y, s, fontName="Helvetica-Bold" if bold else "Helvetica",
                          fontSize=size, fillColor=self._c(color), textAnchor=anchor))


def erd_drawing(lay: Layout) -> Drawing:
    d = Drawing(lay.width, lay.height)
    draw_erd(RLCanvas(lay.height, d), lay)
    return d
