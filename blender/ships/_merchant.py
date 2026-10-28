"""Pieces shared by the big merchant ships (container, tanker): hull with bulb, rudder and
propeller, forecastle and foremast, the aft house with bridge and wings, funnel, main mast with
radars, lifeboat davits, mooring stations and a generic slewing/luffing crane.

All positions are in the ship frame (metres, +X bow, +Y port, +Z up, origin waterline amidships).
"""

import math

from mathutils import Matrix

from ._hull import HullForm, smooth

BLACK = (0.04, 0.04, 0.045)
GLASS = (0.06, 0.09, 0.12)
STEEL = (0.45, 0.47, 0.5)
LIFEBOAT = (0.95, 0.42, 0.05)
TIER_H = 2.8


def merchant_form(p, fc_from_xi=0.86, midbody=(-0.45, 0.25)):
    L, B, T, D = p["loa_m"], p["beam_m"], p["draught_m"], p["depth_m"]
    F = D - T
    fc_h = p.get("forecastle_height_m", 2.6)
    aft_a, fwd_a = midbody

    def deck_z(xi):
        return F + fc_h * smooth(fc_from_xi - 0.004, fc_from_xi, xi) + 0.6 * smooth(0.5, 1.0, xi)

    def keel_z(xi):
        if xi < -0.62:
            t = (-0.62 - xi) / 0.38
            return -T + (T + 0.04 * T) * t
        if xi > 0.9:
            return -T + 0.35 * T * smooth(0.9, 1.0, xi)
        return -T

    def half_wl(xi):
        if xi > fwd_a:
            u = min(1.0, (xi - fwd_a) / (0.985 - fwd_a))
            return max(0.0, 1 - u * u) ** 0.75
        if xi < aft_a:
            u = (aft_a - xi) / (1 + aft_a)
            return 1 - 0.55 * u ** 1.6
        return 1.0

    def half_deck(xi):
        if xi > 0.35:
            u = min(1.0, (xi - 0.35) / 0.65)
            return max(0.0, 1 - u * u) ** 0.5
        if xi < -0.6:
            u = (-0.6 - xi) / 0.4
            return 1 - 0.14 * u * u
        return 1.0

    def fullness(xi):
        if -0.4 < xi < 0.2:
            return 10.0
        if xi >= 0.2:
            return 10.0 - 7.5 * smooth(0.2, 0.85, xi)
        return 10.0 - 7.0 * smooth(0.4, 0.85, -xi)

    form = HullForm(L, B, deck_z, keel_z, half_wl, half_deck, fullness,
                    rake_m=0.045 * L, rake_from_xi=0.7)
    form.fc_x = fc_from_xi * L / 2
    form.freeboard = F
    form.fc_deck = F + fc_h
    return form


def build_hull(me3d, p, form):
    """Hull__Main (+skeg), Hull__Bulb, Hull__Rudder (moving), Hull__Propeller."""
    L, B, T = p["loa_m"], p["beam_m"], p["draught_m"]
    hull_m = me3d.material(p["hull_color"], "hull_topsides")
    boot_m = me3d.material(p["boot_color"], "hull_antifouling")
    deck_m = me3d.material(p["deck_color"], "deck")
    mb = me3d.MeshBuilder()
    fc = form.fc_x / (L / 2)
    mb.loft(form.sections(96, extra_xi=(fc - 0.004, fc, 0.985, 0.995)),
            lambda zc: boot_m if zc < -0.02 else hull_m, close_top=True, top_mat=deck_m)
    # rudder and propeller geometry (shared numbers)
    c = 0.035 * L                      # rudder chord
    x_r = -L / 2 + 0.7 * c + 0.4      # rudder stock
    x_p = x_r + 0.3 * c + 0.012 * L   # propeller plane
    r_p = 0.3 * T
    z_hub = -0.6 * T
    # skeg and stern boss: a centre plate from the aft end of the flat keel to the shaft
    x_a = -0.62 * L / 2
    poly = [(x_a, -T), (x_p + 1.2, z_hub - 0.7), (x_p + 1.2, form.keel_at(x_p + 1.2) + 1.0),
            (x_a + 2.0, -T + 1.0)]
    mb.prism_xz(poly, -0.025 * B, 0.025 * B, boot_m)
    mb.cylinder((x_p + 0.6, 0, z_hub), (x_p + 4.0, 0, z_hub), 0.16 * r_p * 2, boot_m, 16)
    hull = mb.to_object("Hull__Main", pivot=(0, 0, 0))

    # bulbous bow
    bl = 0.05 * L
    bx = form.stem_x(-0.6 * T) - 0.1 * bl
    bulb = me3d.MeshBuilder().ellipsoid((bx, 0, -0.6 * T), (bl / 2, 0.11 * B, 0.24 * T),
                                        boot_m, 16, 10)
    bulb.to_object("Hull__Bulb", pivot=(bx, 0, -0.6 * T), parent=hull)

    # rudder: a plate hung from its stock, which is the pivot
    z_top = form.keel_at(x_r) - 0.3
    z_bot = -0.93 * T
    rud = me3d.MeshBuilder()
    rud.prism_xz([(x_r + 0.3 * c, z_bot + 0.6), (x_r + 0.3 * c, z_top), (x_r - 0.7 * c, z_top),
                  (x_r - 0.7 * c, z_bot), (x_r + 0.1 * c, z_bot)], -0.012 * c * 8, 0.012 * c * 8,
                 boot_m)
    rudder = rud.to_object("Hull__Rudder", pivot=(x_r, 0, z_top), parent=hull)
    me3d.set_joint(rudder, "z", -35, 35, "P1")

    # propeller: hub + blades in the YZ plane
    bronze = me3d.material((0.62, 0.45, 0.2), "bronze", roughness=0.35, metallic=0.9)
    pm = me3d.MeshBuilder()
    pm.cylinder((x_p - 0.6, 0, z_hub), (x_p + 0.8, 0, z_hub), 0.17 * r_p, bronze, 16)
    nb = p.get("propeller_blades", 5)
    for k in range(nb):
        a = 2 * math.pi * k / nb
        rot = Matrix.Rotation(a, 3, "X") @ Matrix.Rotation(math.radians(25), 3, "Z")
        ctr = (x_p, -math.sin(a) * r_p * 0.58, math.cos(a) * r_p * 0.58 + z_hub)
        pm.box_oriented(ctr, (0.12 * r_p, 0.42 * r_p, 0.84 * r_p), rot, bronze)
    pm.to_object("Hull__Propeller", pivot=(x_p, 0, z_hub), parent=hull)

    me3d.add_socket("socket_bow", (form.stem_x(0.0), 0, 0.0), follow=hull)
    me3d.add_socket("socket_prop", (x_p, 0, z_hub), follow=hull)
    me3d.add_socket("socket_light_stern", (-L / 2 + 0.3, 0, form.deck_at(-L / 2) + 1.5),
                    follow=hull)
    return hull


def build_forecastle(me3d, p, form, hull):
    """Foremast with the forward masthead light, windlasses, bow mooring station."""
    L = p["loa_m"]
    x_m = 0.47 * L
    zm = form.deck_at(x_m)
    mast_m = me3d.material(p["mast_color"], "mast")
    h = 0.06 * L
    mm = me3d.MeshBuilder()
    mm.cylinder((x_m, 0, zm - 0.2), (x_m, 0, zm + h), 0.35, mast_m, 12, radius1=0.2)
    mm.box((x_m, 0, zm + 0.62 * h), (0.3, 2.4, 0.25), mast_m)
    fore = mm.to_object("Mast__Fore", pivot=(x_m, 0, zm), parent=hull)
    me3d.add_socket("socket_light_masthead", (x_m, 0, zm + h + 0.3), follow=fore)

    x_w = max(0.445 * L, form.fc_x + 3.5)
    zw = form.deck_at(x_w)
    hb = form.deck_half_breadth(x_w)
    wm = me3d.MeshBuilder()
    for s in (1, -1):
        y = s * min(0.22 * p["beam_m"], hb - 2.0)
        wm.cylinder((x_w, y - 0.9, zw + 1.0), (x_w, y + 0.9, zw + 1.0), 0.9, STEEL, 14)
        wm.box((x_w, y, zw + 0.4), (2.2, 2.2, 0.8), STEEL)
    wm.to_object("Deck__Windlass", pivot=(x_w, 0, zw), parent=hull)

    x_s = form.fc_x + 0.35 * (x_w - form.fc_x)
    me3d.add_station("deck_fwd", (x_s, 0.0, form.deck_at(x_s)), hull, "stand",
                     ["mooring", "anchoring", "lookout"], "Forecastle, mooring station")


def build_aft_deck(me3d, p, form, hull, x_station):
    zd = form.deck_at(x_station)
    wm = me3d.MeshBuilder()
    for s in (1, -1):
        y = s * 0.15 * p["beam_m"]
        wm.cylinder((x_station - 1.0, y, zd), (x_station - 1.0, y, zd + 1.6), 0.8, STEEL, 14)
        wm.cylinder((x_station - 1.0, y - 0.9, zd + 1.2), (x_station - 1.0, y + 0.9, zd + 1.2),
                    0.35, STEEL, 10)
    wm.to_object("Deck__Mooring_Winch_Aft", pivot=(x_station - 1.0, 0, zd), parent=hull)
    me3d.add_station("deck_aft", (x_station + 0.5, 0.0, zd), hull, "stand",
                     ["mooring", "lookout"], "Poop deck, aft mooring station", yaw_deg=180.0)


def build_house(me3d, p, form, hull, x_front):
    """Accommodation, wheelhouse, bridge wings, funnel, main mast, radars, lifeboats.
    Returns a dict of key positions."""
    L, B = p["loa_m"], p["beam_m"]
    tiers = int(p["house_tiers"])
    house_m = me3d.material(p["superstructure_color"], "superstructure")
    glass = me3d.material(GLASS, "glass", roughness=0.15, metallic=0.2)
    z0 = form.deck_at(x_front)
    hl = max(10.0, 0.065 * L)            # house length
    hw = 0.35 * B                        # house half width
    x_back = x_front - hl
    z_top = z0 + tiers * TIER_H          # bridge deck floor

    hm = me3d.MeshBuilder()
    hm.box_minmax((x_back, -hw, z0 - 0.3), (x_front, hw, z_top), house_m)
    for t in range(1, tiers + 1):
        zc = z0 + (t - 0.45) * TIER_H
        hm.box((x_front + 0.04, 0, zc), (0.12, 2 * hw - 1.2, 0.9), glass)
        for s in (1, -1):
            hm.box((x_front - hl / 2, s * (hw + 0.04), zc), (hl - 1.2, 0.12, 0.9), glass)
    house = hm.to_object("Accommodation__House", pivot=(x_front, 0, z0), parent=hull)

    # wheelhouse with a full-width window band and a visor
    wl = min(hl - 1.0, 0.045 * L)
    ww = hw + 0.5
    wm = me3d.MeshBuilder()
    wm.box_minmax((x_front - wl, -ww, z_top), (x_front, ww, z_top + 3.2), house_m)
    wm.box_minmax((x_front - 0.05, -ww + 0.3, z_top + 1.1), (x_front + 0.06, ww - 0.3,
                                                              z_top + 2.6), glass)
    for s in (1, -1):
        wm.box((x_front - wl / 2, s * (ww + 0.03), z_top + 1.85), (wl - 0.6, 0.12, 1.5), glass)
    wm.box_minmax((x_front - wl - 0.2, -ww - 0.2, z_top + 3.2), (x_front + 0.9, ww + 0.2,
                                                                  z_top + 3.5), house_m)
    wheelhouse = wm.to_object("Bridge__Wheelhouse", pivot=(x_front, 0, z_top), parent=house)

    # bridge wings: slabs out to the ship's side, with bulwarks; floor = bridge deck
    y_out = B / 2 - 0.15
    wing_len = 4.0
    wings = {}
    for side, s in (("Port", 1), ("Stbd", -1)):
        bm_ = me3d.MeshBuilder()
        y0, y1 = sorted((s * ww, s * y_out))
        bm_.box_minmax((x_front - wing_len, y0, z_top - 0.6), (x_front, y1, z_top), house_m)
        bm_.box_minmax((x_front - 0.15, y0, z_top), (x_front, y1, z_top + 1.1), house_m)
        bm_.box_minmax((x_front - wing_len, min(s * y_out, s * (y_out - 0.15)), z_top),
                       (x_front, max(s * y_out, s * (y_out - 0.15)), z_top + 1.1), house_m)
        bm_.box((x_front - 1.2, s * (y_out - 0.6), z_top + 0.55), (0.6, 0.6, 1.1), STEEL)  # repeater
        wing = bm_.to_object(f"Bridge__Wing_{side}", pivot=(x_front, s * ww, z_top),
                             parent=wheelhouse)
        wings[side] = wing
        me3d.add_station(f"bridge_wing_{side.lower()}", (x_front - 2.0, s * (y_out - 1.6), z_top),
                         wing, "stand", ["lookout", "con", "mooring"],
                         f"Bridge wing, {'port' if s > 0 else 'starboard'}")
        light = (x_front - 0.5, s * (y_out + 0.05), z_top + 1.6)
        me3d.add_socket("socket_light_port" if s > 0 else "socket_light_stbd", light, follow=wing)

    me3d.add_station("helm", (x_front - 2.0, 0.0, z_top), wheelhouse, "stand",
                     ["steer", "con", "lookout"], "Wheelhouse, helm")
    me3d.add_socket("socket_bridge_eye", (x_front - 1.2, 0.0, z_top + 1.7), follow=wheelhouse)

    # main mast on the wheelhouse roof, two radars on a platform
    mast_m = me3d.material(p["mast_color"], "mast")
    roof = z_top + 3.5
    x_m = x_front - wl * 0.55
    mh = 0.05 * L
    mm = me3d.MeshBuilder()
    mm.cylinder((x_m, 0, roof), (x_m, 0, roof + mh), 0.3, mast_m, 12, radius1=0.18)
    mm.box_minmax((x_m - 2.6, -1.4, roof + 2.6), (x_m + 2.6, 1.4, roof + 2.8), mast_m)
    mm.box((x_m, 0, roof + 0.75 * mh), (0.25, 3.0, 0.2), mast_m)
    mast = mm.to_object("Mast__Main", pivot=(x_m, 0, roof), parent=wheelhouse)
    me3d.add_socket("socket_light_masthead_aft", (x_m, 0, roof + mh + 0.3), follow=mast)
    for k, (dx, span) in enumerate(((1.6, 4.0), (-1.6, 5.5)), start=1):
        rm = me3d.MeshBuilder()
        piv = (x_m + dx, 0, roof + 3.4)
        rm.cylinder((piv[0], 0, roof + 2.8), (piv[0], 0, piv[2]), 0.25, STEEL, 10)
        rm.box((piv[0], 0, piv[2] + 0.2), (0.35, span, 0.4), (0.92, 0.92, 0.9))
        radar = rm.to_object(f"Mast__Radar_{k}", pivot=piv, parent=mast)
        me3d.set_joint(radar, "z", -180, 180, "P0")
        if k == 1:
            me3d.add_socket("socket_radar", (piv[0], 0, piv[2] + 0.3), follow=radar)

    # funnel on an engine casing aft of the house
    fun_m = me3d.material(p["funnel_color"], "funnel")
    band_m = me3d.material(p["funnel_band_color"], "funnel_band")
    cas_len = 0.03 * L
    x_cb = x_back - cas_len
    cz1 = z0 + max(2, tiers - 2) * TIER_H
    cm = me3d.MeshBuilder()
    cm.box_minmax((x_cb, -0.2 * B, z0 - 0.3), (x_back + 0.2, 0.2 * B, cz1), house_m)
    casing = cm.to_object("Funnel__Casing", pivot=(x_back, 0, z0), parent=house)
    fz_top = roof + 4.5
    fx = x_back - cas_len / 2
    flen, fwid = 0.03 * L, 0.24 * B
    rake = 0.15 * (fz_top - cz1)
    fm = me3d.MeshBuilder()

    def band(z_a, z_b, mat):
        ra, rb = rake * (z_a - cz1) / (fz_top - cz1), rake * (z_b - cz1) / (fz_top - cz1)
        poly = [(fx + flen / 2 - ra, z_a), (fx - flen / 2 - ra, z_a),
                (fx - flen / 2 - rb, z_b), (fx + flen / 2 - rb, z_b)]
        fm.prism_xz(poly, -fwid / 2, fwid / 2, mat)

    zs = [cz1, cz1 + 0.55 * (fz_top - cz1), cz1 + 0.8 * (fz_top - cz1), fz_top - 1.2, fz_top]
    band(zs[0], zs[1], fun_m)
    band(zs[1], zs[2], band_m)
    band(zs[2], zs[3], fun_m)
    band(zs[3], zs[4], me3d.material(BLACK, "funnel_top"))
    for dy in (-0.25 * fwid, 0.25 * fwid):
        fm.cylinder((fx - rake, dy, fz_top - 0.5), (fx - rake - 0.3, dy, fz_top + 1.4), 0.55,
                    me3d.material(BLACK, "funnel_top"), 12)
    fm.to_object("Funnel__Main", pivot=(fx, 0, cz1), parent=casing)

    # lifeboats on gravity davits, boat deck two tiers up
    z_bd = z0 + 2 * TIER_H
    x_d = x_back + 0.45 * hl
    lb = me3d.material(p.get("lifeboat_color", LIFEBOAT), "lifeboat")
    blen = min(8.5, hl - 2.0)
    for side, s in (("Port", 1), ("Stbd", -1)):
        piv = (x_d, s * (hw + 0.3), z_bd)
        dm = me3d.MeshBuilder()
        for dx in (-blen / 2 + 0.8, blen / 2 - 0.8):
            dm.box((x_d + dx, piv[1], z_bd + 2.0), (0.4, 0.4, 4.0), STEEL)
            dm.box((x_d + dx, s * (hw + 1.3), z_bd + 3.9), (0.4, 2.2, 0.35), STEEL)
        davit = dm.to_object(f"Lifeboat__Davit_{side}", pivot=piv, parent=house)
        me3d.set_joint(davit, "x", -55 if s > 0 else 0, 0 if s > 0 else 55, "P2")
        boat = me3d.MeshBuilder()
        yc = s * (hw + 2.0)
        boat.ellipsoid((x_d, yc, z_bd + 1.2), (blen / 2, 1.45, 1.0), lb, 14, 8)
        boat.box((x_d, yc, z_bd + 2.0), (blen * 0.7, 2.3, 1.1), lb)
        boat.to_object(f"Lifeboat__Boat_{side}", pivot=(x_d, yc, z_bd + 3.6), parent=davit)

    return {"x_front": x_front, "x_back": x_back, "x_casing_back": x_cb, "z_bridge": z_top,
            "house_half_width": hw, "roof": roof}


def build_crane(me3d, base, x, y, z_deck, pedestal_h, jib_len, color, parent, jib_dir=1,
                slew_limits=(-170, 170), luff_limits=(-75, 0)):
    """Pedestal (fixed) -> slewing house (joint z) -> jib (joint y, luffing).
    The jib rests horizontal pointing ``jib_dir`` along X; negative luff angles raise it."""
    mat = me3d.material(color, "crane")
    pm = me3d.MeshBuilder()
    r = max(0.6, 0.11 * pedestal_h)
    pm.cylinder((x, y, z_deck), (x, y, z_deck + pedestal_h), r, mat, 16)
    ped = pm.to_object(f"{base}__Pedestal", pivot=(x, y, z_deck), parent=parent)
    zt = z_deck + pedestal_h
    hs = max(1.6, 0.13 * jib_len)
    sm = me3d.MeshBuilder()
    sm.box((x - jib_dir * 0.2 * hs, y, zt + hs / 2), (hs * 1.3, hs, hs), mat)
    sm.box((x - jib_dir * 0.5 * hs, y, zt + hs * 1.25), (0.3, 0.3, hs * 0.5), mat)
    slew = sm.to_object(base, pivot=(x, y, zt), parent=ped)
    me3d.set_joint(slew, "z", slew_limits[0], slew_limits[1], "P0")
    jz = zt + 0.45 * hs
    jx = x + jib_dir * 0.45 * hs
    jm = me3d.MeshBuilder()
    w0 = max(0.35, 0.05 * jib_len)
    jm.cylinder((jx, y, jz), (jx + jib_dir * jib_len, y, jz), w0, mat, 8, radius1=w0 * 0.45)
    jm.box((jx + jib_dir * jib_len, y, jz - 0.6), (0.3, 0.3, 1.2), STEEL)  # hook block
    jib = jm.to_object(f"{base}__Jib", pivot=(jx, y, jz), parent=slew)
    lo, hi = luff_limits
    if jib_dir < 0:  # pointing aft, raising is a positive rotation about Y
        lo, hi = -hi, -lo
    me3d.set_joint(jib, "y", lo, hi, "P1")
    return ped, slew, jib
