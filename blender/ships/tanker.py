"""Tanker: a crude / product tanker (Aframax-like by default) with the house aft, a long flat
deck, longitudinal cargo pipelines, a cargo manifold amidships, a raised catwalk, tank hatches
and a provision crane by the house.

Knobs are documented in catalog/ships/tanker.json ("param_docs").
"""

from . import _merchant as M

TRI_BUDGET = 200_000


def build(p, me3d):
    L, B = float(p["loa_m"]), float(p["beam_m"])
    if not (50 <= L <= 400):
        raise ValueError(f"loa_m {L} is outside 50..400 m for a tanker")
    form = M.merchant_form(p, fc_from_xi=0.88, midbody=(-0.5, 0.3))
    hull = M.build_hull(me3d, p, form)
    M.build_forecastle(me3d, p, form, hull)
    house = M.build_house(me3d, p, form, hull, float(p["house_front_frac"]) * L)
    M.build_aft_deck(me3d, p, form, hull, (house["x_casing_back"] - L / 2) / 2)

    zd = form.freeboard
    x_a, x_f = house["x_front"] + 3.0, form.fc_x - 3.0
    pipe_m = me3d.material(p["pipe_color"], "pipework", roughness=0.5)
    steel = me3d.material(M.STEEL, "steel")

    # cargo pipelines along the starboard side of the catwalk, on supports every 8 m
    pm = me3d.MeshBuilder()
    n = int(p["pipelines"])
    ys = [-1.6 - 1.1 * k for k in range(n)]
    for y in ys:
        pm.cylinder((x_a, y, zd + 0.9), (x_f, y, zd + 0.9), 0.32, pipe_m, 10, caps=True)
    x = x_a
    while x <= x_f:
        pm.box((x, (ys[0] + ys[-1]) / 2 if ys else -2, zd + 0.3), (0.3, 1.1 * max(1, n) + 0.4, 0.6),
               steel)
        x += 8.0
    pm.to_object("Deck__Pipeline", pivot=(x_a, 0, zd), parent=hull)

    # manifold: crossovers to both sides with risers and flanged ends, plus a hose saddle
    xm = float(p["manifold_x_frac"]) * L
    mm = me3d.MeshBuilder()
    y_side = B / 2 - 2.2
    for k in range(int(p["manifold_connections"])):
        xk = xm + (k - (int(p["manifold_connections"]) - 1) / 2) * 2.2
        mm.cylinder((xk, -y_side, zd + 0.9), (xk, y_side, zd + 0.9), 0.3, pipe_m, 10)
        for s in (1, -1):
            mm.cylinder((xk, s * y_side, zd + 0.9), (xk, s * y_side, zd + 1.8), 0.3, pipe_m, 10)
            mm.cylinder((xk, s * y_side, zd + 1.8), (xk, s * (y_side + 0.9), zd + 1.8), 0.3,
                        pipe_m, 10)
            mm.cylinder((xk, s * (y_side + 0.85), zd + 1.8), (xk, s * (y_side + 1.0), zd + 1.8),
                        0.5, steel, 12)
    for s in (1, -1):
        mm.box((xm, s * (y_side - 0.6), zd + 0.6), (2.2 * int(p["manifold_connections"]) + 2,
                                                     2.0, 1.2), steel)
    mm.to_object("Deck__Manifold", pivot=(xm, 0, zd), parent=hull)

    # catwalk: raised walkway on the centreline from the house to the forecastle
    cw = me3d.MeshBuilder()
    zc = zd + 2.6
    cw.box_minmax((x_a - 2.0, -0.6, zc - 0.15), (x_f, 0.6, zc), steel)
    for s in (1, -1):
        cw.box_minmax((x_a - 2.0, s * 0.6 - 0.04, zc + 1.0), (x_f, s * 0.6 + 0.04, zc + 1.08), steel)
    x = x_a
    while x <= x_f:
        cw.box((x, 0, (zd + zc) / 2), (0.25, 0.25, zc - zd), steel)
        for s in (1, -1):
            cw.box((x, s * 0.6, zc + 0.5), (0.08, 0.08, 1.0), steel)
        x += 6.0
    cw.to_object("Deck__Catwalk", pivot=(x_a, 0, zc), parent=hull)

    # tank hatches: a pair per cargo tank
    hm = me3d.MeshBuilder()
    nt = int(p["cargo_tanks"])
    for k in range(nt):
        xk = x_a + (k + 0.5) * (x_f - x_a) / nt
        for s in (1, -1):
            hm.cylinder((xk, s * 0.2 * B, zd), (xk, s * 0.2 * B, zd + 0.9), 0.75, steel, 12)
    hm.to_object("Deck__Tank_Hatches", pivot=(x_a, 0, zd), parent=hull)

    # provision crane on the port side ahead of the house
    xc = house["x_front"] + 4.0
    yc = min(B / 2 - 2.5, house["house_half_width"] + 3.0)
    M.build_crane(me3d, "Deck__Provision_Crane", xc, yc, zd, 3.5, float(p["provision_crane_jib_m"]),
                  p["crane_color"], hull, jib_dir=1, luff_limits=(-75, 0))
