#!/usr/bin/env python3
"""The Banana Straightener - a catalogue photograph of an impossible gadget.

Pure Python 3.13 stdlib. Draws a 1024x1024 studio product shot into
/output/entry.png (or $MAKEFUN_OUTPUT_DIR/entry.png): a sleek white
countertop machine with a curved banana sliding in on the left and a
perfectly straight banana coming out on the right, plus one spare banana
lying on the studio floor as the single accessory.

Deterministic: no randomness, no time, no dict-order dependence.
"""
import math
import os
import struct
import zlib

W, H = 1024, 1024

# ---------------------------------------------------------------- framebuffer
buf = bytearray(W * H * 3)


def _idx(x, y):
    return (y * W + x) * 3


def set_px(x, y, rgb):
    if 0 <= x < W and 0 <= y < H:
        i = _idx(x, y)
        buf[i], buf[i + 1], buf[i + 2] = rgb


def blend_px(x, y, rgb, a):
    """Blend rgb over the pixel at (x, y); a in 0..255."""
    if 0 <= x < W and 0 <= y < H and a > 0:
        i = _idx(x, y)
        if a >= 255:
            buf[i], buf[i + 1], buf[i + 2] = rgb
            return
        ia = 255 - a
        buf[i] = (rgb[0] * a + buf[i] * ia) // 255
        buf[i + 1] = (rgb[1] * a + buf[i + 1] * ia) // 255
        buf[i + 2] = (rgb[2] * a + buf[i + 2] * ia) // 255


def fill_rect(x0, y0, x1, y1, rgb):
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(W, x1)
    y1 = min(H, y1)
    if x0 >= x1 or y0 >= y1:
        return
    row = bytes(rgb) * (x1 - x0)
    for y in range(y0, y1):
        s = _idx(x0, y)
        buf[s:s + len(row)] = row


def vgrad(y0, y1, top, bot):
    """Vertical gradient over the full width between y0 and y1."""
    span = max(1, y1 - y0)
    for y in range(max(0, y0), min(H, y1)):
        t = (y - y0) / span
        c = tuple(int(top[k] + (bot[k] - top[k]) * t) for k in range(3))
        row = bytes(c) * W
        s = _idx(0, y)
        buf[s:s + len(row)] = row


def fill_ellipse(cx, cy, rx, ry, rgb, alpha=255):
    rx = max(1, rx)
    ry = max(1, ry)
    for y in range(max(0, cy - ry), min(H, cy + ry + 1)):
        dy = (y - cy) / ry
        dx = rx * math.sqrt(max(0.0, 1.0 - dy * dy))
        x0 = max(0, int(cx - dx))
        x1 = min(W, int(cx + dx) + 1)
        if alpha >= 255:
            row = bytes(rgb) * (x1 - x0)
            s = _idx(x0, y)
            buf[s:s + len(row)] = row
        else:
            for x in range(x0, x1):
                blend_px(x, y, rgb, alpha)


def fill_poly(pts, rgb, alpha=255):
    """Scanline fill of a simple polygon (list of (x, y))."""
    if len(pts) < 3:
        return
    ys = [p[1] for p in pts]
    y0 = max(0, int(min(ys)))
    y1 = min(H - 1, int(max(ys)) + 1)
    n = len(pts)
    for y in range(y0, y1 + 1):
        xs = []
        for i in range(n):
            x0, y0p = pts[i]
            x1, y1p = pts[(i + 1) % n]
            if (y0p <= y < y1p) or (y1p <= y < y0p):
                t = (y - y0p) / (y1p - y0p)
                xs.append(x0 + t * (x1 - x0))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            xa = max(0, int(xs[k]))
            xb = min(W, int(xs[k + 1]) + 1)
            if alpha >= 255:
                row = bytes(rgb) * (xb - xa)
                s = _idx(xa, y)
                buf[s:s + len(row)] = row
            else:
                for x in range(xa, xb):
                    blend_px(x, y, rgb, alpha)


def fill_rr(x0, y0, x1, y1, r, rgb, alpha=255):
    fill_rect(x0 + r, y0, x1 - r, y1, rgb)
    fill_rect(x0, y0 + r, x1, y1 - r, rgb)
    fill_ellipse(x0 + r, y0 + r, r, r, rgb, alpha)
    fill_ellipse(x1 - r, y0 + r, r, r, rgb, alpha)
    fill_ellipse(x0 + r, y1 - r, r, r, rgb, alpha)
    fill_ellipse(x1 - r, y1 - r, r, r, rgb, alpha)


def stamp_circle(cx, cy, r, rgb, alpha=255):
    fill_ellipse(int(cx), int(cy), int(r), int(r), rgb, alpha)


def thick_curve(p0, p1, p2, radius, rgb, steps=90):
    """Quadratic bezier stamped with circles -> a smooth thick curve."""
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0]
        y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]
        stamp_circle(x, y, radius, rgb)


def thick_line(p0, p1, radius, rgb, steps=60):
    for i in range(steps + 1):
        t = i / steps
        x = p0[0] + t * (p1[0] - p0[0])
        y = p0[1] + t * (p1[1] - p0[1])
        stamp_circle(x, y, radius, rgb)


# ---------------------------------------------------------------- 5x7 font
FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "0": ("01110", "10011", "10101", "11001", "10001", "10001", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "-": ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}


def draw_text(s, x, y, scale, rgb):
    cx = x
    for ch in s:
        g = FONT.get(ch, FONT[" "])
        for row in range(7):
            bits = g[row]
            for col in range(5):
                if bits[col] == "1":
                    fill_rect(cx + col * scale, y + row * scale,
                              cx + (col + 1) * scale, y + (row + 1) * scale, rgb)
        cx += 6 * scale


def text_width(s, scale):
    return len(s) * 6 * scale - scale


# ---------------------------------------------------------------- scene
def banana_yellow(t):
    """Yellow shading along a banana: 0.0 dark edge -> 1.0 bright centre."""
    return (247, 213, 74)


def draw_banana_curve(p0, p1, p2, radius):
    # body
    thick_curve(p0, p1, p2, radius, (247, 213, 74), steps=110)
    # top highlight, offset a little up
    hp0 = (p0[0], p0[1] - 7)
    hp1 = (p1[0], p1[1] - 9)
    hp2 = (p2[0], p2[1] - 7)
    thick_curve(hp0, hp1, hp2, max(5, radius - 13), (251, 231, 122), steps=90)
    # stem nub at the free end
    stamp_circle(p0[0] - 6, p0[1] - 2, 7, (111, 90, 46))
    fill_rect(int(p0[0]) - 16, int(p0[1]) - 6, int(p0[0]) - 4, int(p0[1]) + 4,
              (111, 90, 46))


def draw_banana_straight(p0, p1, radius):
    thick_line(p0, p1, radius, (247, 213, 74), steps=70)
    # highlight along the top
    thick_line((p0[0], p0[1] - 7), (p1[0], p1[1] - 7), max(5, radius - 13),
               (251, 231, 122), steps=60)
    # brown tip at the far end
    stamp_circle(p1[0] + 4, p1[1] - 1, 6, (138, 107, 58))


def render():
    # --- studio backdrop: soft vertical gradient, lighter sweep behind product
    vgrad(0, 800, (247, 247, 249), (226, 227, 231))
    vgrad(800, H, (222, 223, 227), (205, 206, 211))
    # soft halo behind the product
    fill_ellipse(512, 500, 480, 210, (242, 242, 245))
    # faint floor line
    fill_rect(0, 799, W, 801, (196, 197, 202))

    # --- soft shadows on the floor
    fill_ellipse(512, 812, 330, 24, (60, 62, 70), alpha=46)
    fill_ellipse(815, 928, 150, 13, (60, 62, 70), alpha=40)
    fill_ellipse(140, 668, 85, 11, (60, 62, 70), alpha=30)

    # --- slot backing (dark tunnel the bananas pass through)
    fill_rr(186, 482, 838, 532, 22, (32, 34, 39))
    fill_rect(200, 526, 824, 532, (74, 78, 86))

    # --- bananas
    # curved banana sliding in from the left
    draw_banana_curve((55, 480), (120, 590), (250, 507), 20)
    # straight banana coming out on the right
    draw_banana_straight((786, 507), (956, 492), 19)

    # --- machine body, split by the slot: top half and bottom half
    # top half
    fill_rr(198, 378, 826, 482, 26, (185, 189, 198))
    fill_rr(200, 380, 824, 480, 24, (253, 253, 254))
    # chrome strip along the top edge
    fill_rect(224, 384, 800, 392, (205, 208, 214))
    fill_rect(224, 392, 800, 396, (238, 239, 242))
    # bottom half
    fill_rr(198, 530, 826, 622, 26, (185, 189, 198))
    fill_rr(200, 532, 824, 620, 24, (244, 245, 247))
    # slot lips (chrome edges framing the tunnel)
    fill_rect(200, 476, 824, 483, (201, 204, 210))
    fill_rect(200, 530, 824, 537, (201, 204, 210))
    # feet
    fill_rr(280, 620, 330, 640, 8, (70, 73, 80))
    fill_rr(694, 620, 744, 640, 8, (70, 73, 80))

    # --- product label on the top half
    label = "BANANA STRAIGHTENER"
    draw_text(label, 512 - text_width(label, 3) // 2, 408, 3, (42, 46, 53))
    # --- controls on the bottom half
    draw_text("MODEL BS-3000", 268, 566, 2, (74, 79, 88))
    # dial
    stamp_circle(690, 578, 13, (228, 229, 233))
    fill_ellipse(690, 578, 13, 13, (228, 229, 233))
    # dial ring + tick (approximated with small rects/circles)
    for ang in range(0, 360, 45):
        rad = math.radians(ang)
        stamp_circle(690 + 10 * math.cos(rad), 578 + 10 * math.sin(rad), 1,
                     (120, 124, 132))
    stamp_circle(690 + 7, 578 - 7, 2, (90, 94, 102))
    # green power button
    stamp_circle(758, 578, 14, (46, 160, 90))
    stamp_circle(755, 575, 5, (120, 220, 165))

    # --- the single accessory: one spare banana lying on the floor
    draw_banana_curve((690, 888), (800, 948), (946, 882), 18)


def write_png(path):
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        s = y * W * 3
        raw += buf[s:s + W * 3]

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        c += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        return c

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def main():
    render()
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    write_png(os.path.join(outdir, "entry.png"))


if __name__ == "__main__":
    main()
