"""Sampan / bumboat: a 7-9 m open wooden Singapore/Malay boat with a raised bow, floorboards,
thwarts, a small foredeck, an awning on four posts and an outboard on the transom.

Lessons carried over from StraitsSim's sampan reviews (docs/ship-realism/sampan-review.md):
the hull is an OPEN shell with real thickness (a sealed hull with a lid hid all the gear), and
the outboard nests steering inside tilt at its transom bracket so the clamps stay put.

The outboard's skeg reaches exactly the stated draught, so the lowest point of the model is
minus ``draught_m`` (the hull keel stops just above it, as on the real boat).

Knobs are documented in catalog/ships/sampan.json ("param_docs").
"""

import math

from mathutils import Matrix

from ._hull import HullForm, smooth

TRI_BUDGET = 50_000
OB_AFT = 0.67      # outboard overhang aft of the transom (pivot set-back + cowl), metres


def sampan_form(p):
    loa, B, T, D = p["loa_m"], p["beam_m"], p["draught_m"], p["depth_m"]
    Lh = loa - OB_AFT
    F = D - T
    rise = p["bow_rise_m"]
    keel = T - 0.02  # hull keel just above the outboard skeg

    def deck_z(xi):
        return F + rise * smooth(0.25, 1.0, xi) ** 1.6 + 0.1 * smooth(0.6, 1.0, -xi)

    def keel_z(xi):
        if xi > 0.55:
            return -keel + (keel + 0.15) * smooth(0.55, 1.0, xi)
        if xi < -0.75:
            return -keel + 0.12 * smooth(0.75, 1.0, -xi)
        return -keel

    def half_deck(xi):
        if xi > 0.15:
            u = min(1.0, (xi - 0.15) / 0.85)
            return max(0.0, 1 - u * u) ** 0.6
        if xi < -0.2:
            u = (-0.2 - xi) / 0.8
            return 1 - 0.38 * u * u
        return 1.0

    def half_wl(xi):
        return 0.84 * half_deck(xi)

    def fullness(xi):
        return 2.4 + 1.2 * smooth(0.2, 1.0, -xi)

    f = HullForm(Lh, B, deck_z, keel_z, half_wl, half_deck, fullness, rake_m=0.12 * Lh,
                 rake_from_xi=0.5)
    f.Lh = Lh
    return f


def _rail(mb, pts, mat, w=0.07, h=0.09):
    """A rectangular rail swept along a polyline of (x, y, z) points on one side."""
    s = 1 if pts[len(pts) // 2][1] >= 0 else -1
    verts, faces = [], []
    for x, y, z in pts:
        yo, yi = y + s * 0.02, y - s * (w - 0.02)
        verts += [(x, yo, z - h * 0.6), (x, yo, z + h * 0.4), (x, yi, z + h * 0.4),
                  (x, yi, z - h * 0.6)]
    for i in range(len(pts) - 1):
        a, b = 4 * i, 4 * (i + 1)
        for k in range(4):
            k2 = (k + 1) % 4
            faces.append((a + k, a + k2, b + k2, b + k))
    faces.append((3, 2, 1, 0))
    n = 4 * (len(pts) - 1)
    faces.append((n, n + 1, n + 2, n + 3))
    mb.add(verts, faces, mat)


def build(p, me3d):
    loa, B, T = float(p["loa_m"]), float(p["beam_m"]), float(p["draught_m"])
    if not (5 <= loa <= 14):
        raise ValueError(f"loa_m {loa} is outside 5..14 m for a sampan")
    form = sampan_form(p)
    Lh = form.Lh
    hull_m = me3d.material(p["hull_color"], "hull_paint", roughness=0.7, double_sided=True)
    boot_m = me3d.material(p["boot_color"], "hull_bottom", roughness=0.8, double_sided=True)
    wood = me3d.material(p["wood_color"], "timber", roughness=0.85)
    trim = me3d.material(p["trim_color"], "gunwale_paint", roughness=0.7)

    # open hull shell with thickness (solidify inward), transom closed
    sections = form.sections(60, extra_xi=(0.99,))
    hb = me3d.MeshBuilder()
    hb.loft(sections, lambda zc: boot_m if zc < -0.02 else hull_m, close_top=False, cap_aft=True)
    hull = hb.to_object("Hull__Main", pivot=(0, 0, 0), recalc_normals=False)
    sol = hull.modifiers.new("Solidify", "SOLIDIFY")
    sol.thickness = 0.035
    sol.offset = -1.0
    sol.use_even_offset = True

    # gunwale rails along the sheer, both sides
    gm = me3d.MeshBuilder()
    for s in (1, -1):
        pts = [(sec[0][0], s * sec[0][1], sec[0][2]) for sec in sections]
        pts = [q for q in pts if abs(q[1]) > 0.02] + [(sections[-1][0][0], 0.0, sections[-1][0][2])]
        _rail(gm, pts, trim)
    gm.to_object("Hull__Gunwale", pivot=(0, 0, form.deck_at(0)), parent=hull)

    # floorboards: flat, following the inside of the hull
    z_f = -T + 0.18
    x0, x1 = -Lh / 2 + 0.12, Lh / 2 - 1.55
    xs = [x0 + (x1 - x0) * i / 16 for i in range(17)]
    half = [max(0.05, form.half_breadth_at(x, z_f) - 0.05) for x in xs]
    poly = [(x, h) for x, h in zip(xs, half)] + [(x, -h) for x, h in reversed(list(zip(xs, half)))]
    fm = me3d.MeshBuilder()
    fm.prism_xy(poly, z_f - 0.03, z_f, wood)
    floor = fm.to_object("Hull__Floorboards", pivot=(0, 0, z_f), parent=hull)

    # thwarts (benches)
    z_t = z_f + 0.38
    x_ta = -Lh / 2 + 0.55
    for name, x in (("Thwart_Aft", x_ta), ("Thwart_Mid", -0.3), ("Thwart_Fwd", Lh / 2 - 2.0)):
        w = 2 * (form.half_breadth_at(x, z_t) - 0.04)
        tm = me3d.MeshBuilder()
        tm.box((x, 0, z_t - 0.02), (0.26, w, 0.04), wood)
        tm.box((x, 0, (z_f + z_t) / 2), (0.06, 0.06, z_t - z_f - 0.04), wood)
        tm.to_object(f"Hull__{name}", pivot=(x, 0, z_t), parent=hull)

    # small foredeck the bowman stands on
    x_fd = Lh / 2 - 1.5
    z_fd = form.deck_at(x_fd) - 0.12
    xs = [x_fd + i * 0.1 for i in range(16)]
    pts = [(x, form.half_breadth_at(x, z_fd) - 0.05) for x in xs]
    pts = [(x, h) for x, h in pts if h > 0.06]
    poly = pts + [(x, -h) for x, h in reversed(pts)]
    dm = me3d.MeshBuilder()
    dm.prism_xy(poly, z_fd - 0.04, z_fd, wood)
    # bulkhead under the foredeck's aft edge, cut to the inside of the hull
    zs = [z_f + (z_fd - z_f) * k / 8 for k in range(9)]
    prof = [(max(0.02, form.half_breadth_at(x_fd, z) - 0.04), z) for z in zs]
    ring = [(y, z) for y, z in prof] + [(-y, z) for y, z in reversed(prof)]
    n = len(ring)
    verts = [(x_fd, y, z) for y, z in ring] + [(x_fd + 0.04, y, z) for y, z in ring]
    faces = [tuple(range(n)), tuple(n + i for i in reversed(range(n)))]
    faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    dm.add(verts, faces, wood)
    foredeck = dm.to_object("Hull__Foredeck", pivot=(x_fd, 0, z_fd), parent=hull)

    # painted eyes on the bow (oculus), one each side
    if p["eyes"]:
        xi_e, z_e = 0.78, form.deck_z(0.78) - 0.22
        x_e = form.x_of(xi_e, z_e)
        y_e = form.half_breadth_at(x_e, z_e)
        for side, s in (("Port", 1), ("Stbd", -1)):
            em = me3d.MeshBuilder()
            em.cylinder((x_e, s * (y_e - 0.03), z_e), (x_e, s * (y_e + 0.012), z_e), 0.09,
                        (0.95, 0.95, 0.92), 16)
            em.cylinder((x_e + 0.02, s * (y_e - 0.03), z_e), (x_e + 0.02, s * (y_e + 0.02), z_e),
                        0.045, (0.03, 0.03, 0.03), 12)
            em.to_object(f"Hull__Eye_{side}", pivot=(x_e, s * y_e, z_e), parent=hull)

    # awning on four posts
    roof = None
    if p["canopy"]:
        ca, cf = float(p["canopy_aft_x_m"]), float(p["canopy_fwd_x_m"])
        z_r = z_f + float(p["canopy_height_m"])
        post = me3d.MeshBuilder()
        ys = {}
        for x in (ca, cf):
            y = form.half_breadth_at(x, form.deck_at(x)) - 0.06
            ys[x] = y
            for s in (1, -1):
                post.cylinder((x, s * y, form.deck_at(x) - 0.15), (x, s * y, z_r), 0.03, wood, 8)
        posts = post.to_object("Canopy__Posts", pivot=(ca, 0, z_f), parent=hull)
        cloth = me3d.material(p["canopy_color"], "canopy_cloth", roughness=0.9, double_sided=True)
        am = me3d.MeshBuilder()
        nx, ny = 6, 10
        yw = max(ys.values()) + 0.08
        verts, faces = [], []
        for i in range(nx + 1):
            x = ca - 0.12 + (cf - ca + 0.24) * i / nx
            for j in range(ny + 1):
                t = -1 + 2 * j / ny
                verts.append((x, t * yw, z_r + 0.22 * (1 - t * t)))
        for i in range(nx):
            for j in range(ny):
                a = i * (ny + 1) + j
                faces.append((a, a + ny + 1, a + ny + 2, a + 1))
        am.add(verts, faces, cloth)
        roof = am.to_object("Canopy__Awning", pivot=(ca, 0, z_r), parent=posts)
        lp = me3d.MeshBuilder()
        lp.cylinder((cf, 0, z_r + 0.2), (cf, 0, z_r + 0.65), 0.02, (0.2, 0.2, 0.2), 8)
        lp.box((cf, 0, z_r + 0.7), (0.08, 0.08, 0.1), (0.95, 0.95, 0.9))
        lp.to_object("Canopy__Light_Pole", pivot=(cf, 0, z_r + 0.2), parent=roof)
        me3d.add_socket("socket_light_masthead", (cf, 0, z_r + 0.72), follow=roof)
        me3d.add_socket("socket_radar", ((ca + cf) / 2, 0, z_r + 0.3), follow=roof)
        me3d.add_socket("socket_light_stern", (ca - 0.1, 0, z_r + 0.25), follow=roof)
        for s, nm in ((1, "socket_light_port"), (-1, "socket_light_stbd")):
            me3d.add_socket(nm, (cf + 0.04, s * (ys[cf] + 0.04), z_r - 0.1), follow=posts)
    else:
        z_g = form.deck_at(0)
        me3d.add_socket("socket_light_masthead", (x_fd, 0, z_fd + 1.0), follow=hull)
        me3d.add_socket("socket_radar", (0, 0, z_g + 1.0), follow=hull)
        me3d.add_socket("socket_light_stern", (-Lh / 2 + 0.1, 0, z_g + 0.8), follow=hull)
        for s, nm in ((1, "socket_light_port"), (-1, "socket_light_stbd")):
            me3d.add_socket(nm, (x_fd, s * (form.deck_half_breadth(x_fd) - 0.05), z_fd + 0.1),
                            follow=hull)

    # oars lying across the thwarts
    if p["oars"]:
        for side, s in (("Port", 1), ("Stbd", -1)):
            om = me3d.MeshBuilder()
            y = s * 0.45
            om.cylinder((-1.9, y, z_t + 0.03), (1.4, y, z_t + 0.03), 0.025, wood, 8)
            om.box((-2.1, y, z_t + 0.03), (0.5, 0.14, 0.02), wood)
            om.to_object(f"Hull__Oar_{side}", pivot=(0, y, z_t + 0.03), parent=hull)

    # outboard: fixed clamp bracket -> tilt (y) -> steering (z) -> cowl, leg, propeller, tiller
    ob_m = me3d.material(p["outboard_color"], "outboard", roughness=0.4)
    alu = me3d.material((0.6, 0.62, 0.64), "outboard_leg", roughness=0.4, metallic=0.6)
    x_tr = -Lh / 2
    z_tr = form.deck_at(x_tr)
    br = me3d.MeshBuilder()
    br.box((x_tr - 0.04, 0, z_tr - 0.06), (0.14, 0.3, 0.22), alu)
    bracket = br.to_object("Transom__Outboard_Bracket", pivot=(x_tr, 0, z_tr), parent=hull)
    x_t, z_tp = x_tr - 0.12, z_tr - 0.04
    tl = me3d.MeshBuilder()
    tl.cylinder((x_t, -0.16, z_tp), (x_t, 0.16, z_tp), 0.035, alu, 10)
    tl.box((x_t - 0.04, 0, z_tp - 0.12), (0.06, 0.16, 0.26), alu)
    tilt = tl.to_object("Transom__Outboard_Tilt", pivot=(x_t, 0, z_tp), parent=bracket)
    me3d.set_joint(tilt, "y", 0, 70, "P1")
    x_s = x_t - 0.08
    om = me3d.MeshBuilder()
    om.ellipsoid((x_s - 0.22, 0, z_tp + 0.28), (0.27, 0.19, 0.24), ob_m, 14, 8)
    om.box((x_s - 0.16, 0, z_tp + 0.02), (0.22, 0.16, 0.18), ob_m)
    z_g = -T + 0.17
    om.box((x_s - 0.14, 0, (z_tp + z_g) / 2), (0.15, 0.07, z_tp - z_g), alu)
    om.box((x_s - 0.2, 0, -0.1), (0.36, 0.26, 0.02), alu)              # anti-ventilation plate
    om.cylinder((x_s + 0.02, 0, z_g), (x_s - 0.36, 0, z_g), 0.055, alu, 10, radius1=0.04)
    om.box((x_s - 0.2, 0, (z_g - T) / 2), (0.16, 0.02, z_g - (-T)), alu)  # skeg to the draught
    motor = om.to_object("Transom__Outboard", pivot=(x_s, 0, z_tp), parent=tilt)
    me3d.set_joint(motor, "z", -35, 35, "P0")
    pr = me3d.MeshBuilder()
    xp = x_s - 0.4
    pr.cylinder((xp + 0.04, 0, z_g), (xp - 0.06, 0, z_g), 0.035, alu, 8)
    for k in range(3):
        a = 2 * math.pi * k / 3
        rot = Matrix.Rotation(a, 3, "X") @ Matrix.Rotation(math.radians(25), 3, "Z")
        pr.box_oriented((xp, -math.sin(a) * 0.085, z_g + math.cos(a) * 0.085), (0.02, 0.07, 0.11),
                        rot, alu)
    prop = pr.to_object("Transom__Outboard__Propeller", pivot=(xp, 0, z_g), parent=motor)
    ti = me3d.MeshBuilder()
    t0, t1 = (x_s + 0.02, 0, z_tp + 0.12), (x_s + 0.85, 0, z_tp + 0.2)
    ti.cylinder(t0, t1, 0.022, (0.15, 0.15, 0.15), 8)
    ti.cylinder((t1[0] - 0.14, 0, t1[2] - 0.013), (t1[0] + 0.02, 0, t1[2] + 0.002), 0.035,
                (0.1, 0.1, 0.1), 10)
    ti.to_object("Transom__Outboard__Tiller", pivot=t0, parent=motor)
    me3d.add_socket("socket_prop", (xp, 0, z_g), follow=prop)
    me3d.add_socket("socket_bow", (form.stem_x(0.0), 0, 0.0), follow=hull)

    # crew stations: helmsman seated at the tiller, bowman on the foredeck, a passenger
    x_h = x_ta + 0.38
    me3d.add_station("helm", (x_h, -0.32, z_f), floor, "sit", ["steer", "outboard"],
                     "Outboard tiller, helm (seated)")
    me3d.add_socket("socket_bridge_eye", (x_h - 0.2, -0.32, z_t + 0.75), follow=floor)
    me3d.add_station("bow", (x_fd + 0.4, 0, z_fd), foredeck, "stand", ["mooring", "lookout"],
                     "Bow, foredeck")
    me3d.add_station("passenger_1", (-0.3 + 0.45, 0.0, z_f), floor, "sit", ["passenger"],
                     "Passenger, midships")
    return roof
