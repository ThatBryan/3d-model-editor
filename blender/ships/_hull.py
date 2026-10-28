"""Parametric hull form shared by the ship builders.

A hull is described by plan and profile functions of xi = x / (L/2) (-1 transom, +1 stem):

* ``deck_z(xi)``     height of the deck edge (sheer line), metres above the waterline
* ``keel_z(xi)``     height of the keel on the centreline (negative under water)
* ``half_wl(xi)``    half-breadth at the waterline, as a fraction of B/2
* ``half_deck(xi)``  half-breadth at the deck edge, as a fraction of B/2 (flare when > half_wl)
* ``fullness(xi)``   superellipse exponent of the underwater section (2 = round/V, 10 = boxy)

Above the waterline the side is wall-sided with flare growing towards the deck; below it the
section is a superellipse quadrant, so midships get a flat bottom and a round bilge. The stem
is raked by pulling the forward body back at the keel (``rake_m``) while the deck edge still
reaches x = +L/2, so the length overall is exactly L.
"""

import math

ABOVE = 6   # points between deck edge and waterline
BELOW = 9   # points between waterline and keel


class HullForm:
    def __init__(self, L, B, deck_z, keel_z, half_wl, half_deck, fullness,
                 rake_m=0.0, rake_from_xi=0.6):
        self.L, self.B = float(L), float(B)
        self.deck_z, self.keel_z = deck_z, keel_z
        self.half_wl, self.half_deck, self.fullness = half_wl, half_deck, fullness
        self.rake_m, self.rake_from = float(rake_m), rake_from_xi

    # -- profile ------------------------------------------------------------------------------
    def section_yz(self, xi):
        """Port half-section, deck edge -> keel, as (y, z) pairs (constant count)."""
        zd, zk = self.deck_z(xi), self.keel_z(xi)
        zk = min(zk, zd - 0.05)
        zw = max(zk, min(0.0, zd))
        yd = self.B / 2 * max(0.0, self.half_deck(xi))
        yw = self.B / 2 * max(0.0, self.half_wl(xi))
        n = max(1.2, self.fullness(xi))
        pts = []
        for i in range(ABOVE):
            h = 1.0 - i / ABOVE
            pts.append((yw + (yd - yw) * h * h, zw + h * (zd - zw)))
        pts.append((yw, zw))
        for j in range(1, BELOW + 1):
            th = (math.pi / 2) * (j / BELOW) ** 0.8
            c, s = math.cos(th), math.sin(th)
            y = yw * (c ** (2.0 / n) if c > 1e-9 else 0.0)
            z = zw - (zw - zk) * (s ** (2.0 / n))
            pts.append((y if j < BELOW else 0.0, z if j < BELOW else zk))
        return pts

    def x_of(self, xi, z):
        """Stem rake: forward of ``rake_from`` the body shortens towards the keel."""
        x = xi * self.L / 2
        if xi <= self.rake_from or self.rake_m <= 0:
            return x
        xs = self.rake_from * self.L / 2
        zd, zk = self.deck_z(xi), self.keel_z(xi)
        g = max(0.0, min(1.0, (z - zk) / max(1e-6, zd - zk)))
        fk = (self.L / 2 - self.rake_m - xs) / (self.L / 2 - xs)
        return xs + (x - xs) * (fk + (1 - fk) * g ** 1.3)

    def sections(self, n=90, extra_xi=()):
        t = [i / n for i in range(n + 1)]
        xis = sorted(set([round(-1 + 2 * (0.5 - 0.5 * math.cos(math.pi * u)), 5) for u in t]
                         + [round(e, 5) for e in extra_xi]))
        out = []
        for xi in xis:
            out.append([(self.x_of(xi, z), y, z) for y, z in self.section_yz(xi)])
        return out

    # -- queries used to place things on the hull --------------------------------------------
    def deck_half_breadth(self, x):
        return self.B / 2 * max(0.0, self.half_deck(x / (self.L / 2)))

    def xi_at(self, x, z):
        """The section parameter whose (raked) station passes through x at height z."""
        if x >= self.x_of(1.0, z):
            return None
        lo, hi = -1.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if self.x_of(mid, z) < x:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def half_breadth_at(self, x, z):
        """Half-breadth of the hull at x, height z, following the stem rake."""
        xi = self.xi_at(x, z)
        if xi is None:
            return 0.0
        pts = self.section_yz(xi)
        for (y0, z0), (y1, z1) in zip(pts, pts[1:]):
            if min(z0, z1) - 1e-9 <= z <= max(z0, z1) + 1e-9:
                if abs(z1 - z0) < 1e-9:
                    return max(y0, y1)
                return y0 + (y1 - y0) * (z - z0) / (z1 - z0)
        return 0.0

    def deck_at(self, x):
        return self.deck_z(x / (self.L / 2))

    def keel_at(self, x):
        return self.keel_z(x / (self.L / 2))

    def stem_x(self, z):
        return self.x_of(1.0, z)


def smooth(a, b, t):
    """0 below a, 1 above b, smoothstep between."""
    if b == a:
        return 1.0 if t >= b else 0.0
    u = max(0.0, min(1.0, (t - a) / (b - a)))
    return u * u * (3 - 2 * u)
