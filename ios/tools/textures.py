#!/usr/bin/env python3
"""Render the two textures of the iris design - ink and grain - to PNG.

The design draws them with SVG's feTurbulence. Rendering that SVG through
QuickLook flattens it onto white and loses the transparency, which is the
whole texture. So this computes the filter itself, from the reference
implementation in the SVG specification (same lattice, same random
generator, same seed). The result is the pattern from the design, not
something that looks like it.

Standard library only. Takes about half a minute for the ink.
"""
import os
import struct
import sys
import zlib

BSIZE, BM, PERLIN_N = 0x100, 0xFF, 0x1000
RAND_M, RAND_A, RAND_Q, RAND_R = 2147483647, 16807, 127773, 2836


def _setup_seed(s):
    if s <= 0:
        s = -(s % (RAND_M - 1)) + 1
    return min(s, RAND_M - 1)


def _random(s):
    r = RAND_A * (s % RAND_Q) - RAND_R * (s // RAND_Q)
    return r + RAND_M if r <= 0 else r


def _lattice(seed):
    lat = [0] * (BSIZE + BSIZE + 2)
    grad = [[[0.0, 0.0] for _ in range(BSIZE + BSIZE + 2)] for _ in range(4)]
    s = _setup_seed(seed)
    for k in range(4):
        for i in range(BSIZE):
            lat[i] = i
            g = []
            for _ in range(2):
                s = _random(s)
                g.append(((s % (BSIZE + BSIZE)) - BSIZE) / BSIZE)
            n = (g[0] * g[0] + g[1] * g[1]) ** 0.5 or 1.0
            grad[k][i] = [g[0] / n, g[1] / n]
    for i in range(BSIZE - 1, 0, -1):
        k = lat[i]
        s = _random(s)
        j = s % BSIZE
        lat[i], lat[j] = lat[j], k
    for i in range(BSIZE + 2):
        lat[BSIZE + i] = lat[i]
        for k in range(4):
            grad[k][BSIZE + i] = list(grad[k][i])
    return lat, grad


def _noise2(g, lat, x, y):
    t = x + PERLIN_N
    bx0 = int(t) & BM
    bx1 = (bx0 + 1) & BM
    rx0 = t - int(t)
    rx1 = rx0 - 1.0
    t = y + PERLIN_N
    by0 = int(t) & BM
    by1 = (by0 + 1) & BM
    ry0 = t - int(t)
    ry1 = ry0 - 1.0
    i, j = lat[bx0], lat[bx1]
    b00, b10, b01, b11 = lat[i + by0], lat[j + by0], lat[i + by1], lat[j + by1]
    sx = rx0 * rx0 * (3 - 2 * rx0)
    sy = ry0 * ry0 * (3 - 2 * ry0)
    q = g[b00]; u = rx0 * q[0] + ry0 * q[1]
    q = g[b10]; v = rx1 * q[0] + ry0 * q[1]
    a = u + sx * (v - u)
    q = g[b01]; u = rx0 * q[0] + ry1 * q[1]
    q = g[b11]; v = rx1 * q[0] + ry1 * q[1]
    b = u + sx * (v - u)
    return a + sy * (b - a)


def _srgb(c):
    """Filter primitives work in linearRGB; the page shows sRGB."""
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def render(path, width, height, scale, fx, fy, octaves, seed, rgb, a_mul, a_add):
    """feTurbulence type=fractalNoise followed by the design's feColorMatrix.

    The matrix sets RGB to constants and alpha to a_mul * noise + a_add, so
    only the alpha channel (lattice 3) has to be computed.
    """
    lat, grad = _lattice(seed)
    g = grad[3]
    r, gr, b = (round(_srgb(c) * 255) for c in rgb)
    rows = []
    for py in range(height):
        y0 = (py + 0.5) / scale
        row = bytearray()
        for px in range(width):
            x, y, total, ratio = (px + 0.5) / scale * fx, y0 * fy, 0.0, 1.0
            for _ in range(octaves):
                total += _noise2(g, lat, x, y) / ratio
                x, y, ratio = x * 2, y * 2, ratio * 2
            a = min(1.0, max(0.0, (total + 1) / 2))
            a = min(1.0, max(0.0, a_mul * a + a_add))
            row += bytes((r, gr, b, round(a * 255)))
        rows.append(bytes(row))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + row for row in rows)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n"
                 + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Iris", "Assets.xcassets")
    # The ink of the surfaces: design/Main.dc.html, .inked - 600 x 400 units,
    # drawn at twice the size so it stays smooth on a 3x screen.
    render(os.path.join(assets, "Tinte.imageset", "tinte.png"), 1200, 800, 2,
           0.004, 0.009, 2, 7, (0.95, 0.88, 0.71), 1.5, -0.42)
    # The grain over everything: .korn - a 160-unit tile, at 3x for the phone.
    render(os.path.join(assets, "Korn.imageset", "korn.png"), 480, 480, 3,
           0.9, 0.9, 1, 5, (1.0, 0.98, 0.93), 0.06, 0.0)
    print("Tinte und Korn gerechnet", file=sys.stderr)
