"""
幻想時計3DCG: Pinterestの4枚(時計×星空)を3DCGで再現する。
使い方: blender --background --python clockscenes.py -- <scene 1-4> <out.png> [preview 0/1]
時計・歯車・柱などの人工物はbpyで直接組み立て、宇宙飛行士だけMeshy glb(assets/astronaut.glb)。
"""
import bpy, bmesh, math, os, sys, random
from mathutils import Vector, Quaternion

argv = sys.argv[sys.argv.index("--") + 1:]
SID = int(argv[0]); OUT = argv[1]; PREVIEW = len(argv) > 2 and argv[2] == "1"
WORKSPACE = os.environ.get("GITHUB_WORKSPACE", os.getcwd())
RES = {1: (720, 1280), 2: (720, 940), 3: (720, 1320), 4: (720, 1280)}[SID]
if PREVIEW:
    RES = (RES[0] // 2, RES[1] // 2)
SAMPLES = 8 if PREVIEW else 40
random.seed(SID * 101)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
R = random.Random(SID)


# ---------- 素材 ----------
def M(name, color=(1, 1, 1), emit=0.0, ecolor=None, metal=0.0, rough=0.5, alpha=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit > 0:
        b.inputs["Emission Color"].default_value = (*(ecolor or color), 1)
        b.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
    return m


def starfield(nt, coord, star_scale, neb_scale, base, c1, c2, neb_k, star_k=9.0):
    """星+星雲の色ソケットを返す。coordは座標ソケット。"""
    N = nt.nodes; L = nt.links
    vor = N.new("ShaderNodeTexVoronoi"); vor.feature = "F1"; vor.inputs["Scale"].default_value = star_scale
    L.new(coord, vor.inputs["Vector"])
    rs = N.new("ShaderNodeValToRGB"); rs.color_ramp.elements[0].position = 0.0
    rs.color_ramp.elements[0].color = (star_k, star_k, star_k, 1)
    rs.color_ramp.elements[1].position = 0.035; rs.color_ramp.elements[1].color = (0, 0, 0, 1)
    L.new(vor.outputs["Distance"], rs.inputs["Fac"])
    noi = N.new("ShaderNodeTexNoise"); noi.inputs["Scale"].default_value = neb_scale
    noi.inputs["Detail"].default_value = 8; noi.inputs["Roughness"].default_value = 0.6
    L.new(coord, noi.inputs["Vector"])
    rn = N.new("ShaderNodeValToRGB")
    rn.color_ramp.elements[0].position = 0.4; rn.color_ramp.elements[0].color = (0, 0, 0, 1)
    e = rn.color_ramp.elements.new(0.62); e.color = (*c1, 1)
    rn.color_ramp.elements[2].position = 0.95; rn.color_ramp.elements[2].color = (*c2, 1)
    L.new(noi.outputs["Fac"], rn.inputs["Fac"])
    sc_ = N.new("ShaderNodeVectorMath"); sc_.operation = "SCALE"; sc_.inputs["Scale"].default_value = neb_k
    L.new(rn.outputs["Color"], sc_.inputs[0])
    a1 = N.new("ShaderNodeVectorMath"); a1.operation = "ADD"
    L.new(rs.outputs["Color"], a1.inputs[0]); L.new(sc_.outputs["Vector"], a1.inputs[1])
    a2 = N.new("ShaderNodeVectorMath"); a2.operation = "ADD"; a2.inputs[1].default_value = base
    L.new(a1.outputs["Vector"], a2.inputs[0])
    return a2.outputs["Vector"]


def world(star_scale=260, neb_scale=2.0, base=(0.003, 0.006, 0.03), c1=(0.02, 0.08, 0.6), c2=(0.1, 0.5, 1.0),
          neb_k=1.0, strength=1.0):
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    nt = w.node_tree; nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    col = starfield(nt, tc.outputs["Generated"], star_scale, neb_scale, base, c1, c2, neb_k)
    bg = nt.nodes.new("ShaderNodeBackground"); bg.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(col, bg.inputs["Color"]); nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return w


def star_mat(name, scale, neb_scale, base, c1, c2, neb_k):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    col = starfield(nt, tc.outputs["Object"], scale, neb_scale, base, c1, c2, neb_k, star_k=7.0)
    em = nt.nodes.new("ShaderNodeEmission"); out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(col, em.inputs["Color"]); nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


# ---------- ジオメトリ ----------
def _fin(o, mat, parent):
    if mat: o.data.materials.append(mat)
    if parent: o.parent = parent
    return o


def torus(Rr, r, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None, seg=72, seg2=12):
    bpy.ops.mesh.primitive_torus_add(major_radius=Rr, minor_radius=r, major_segments=seg, minor_segments=seg2,
                                     location=loc, rotation=rot)
    return _fin(bpy.context.active_object, mat, parent)


def cyl(r, d, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None, v=48):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d, vertices=v, location=loc, rotation=rot)
    return _fin(bpy.context.active_object, mat, parent)


def box(sx, sy, sz, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object; o.scale = (sx, sy, sz)
    return _fin(o, mat, parent)


def sphere(r, loc=(0, 0, 0), mat=None, parent=None, seg=20, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=seg, ring_count=seg // 2, location=loc)
    o = bpy.context.active_object; o.scale = scale
    return _fin(o, mat, parent)


def empty(loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
    o = bpy.data.objects.new("e", None); bpy.context.collection.objects.link(o)
    o.location = loc; o.rotation_euler = rot; o.scale = (scale,) * 3
    return o


def text(s, size, loc, rot, mat, parent=None, extr=0.02):
    c = bpy.data.curves.new("t", "FONT"); c.body = s; c.size = size; c.extrude = extr
    c.align_x = "CENTER"; c.align_y = "CENTER"
    o = bpy.data.objects.new("t", c); bpy.context.collection.objects.link(o)
    o.location = loc; o.rotation_euler = rot; o.data.materials.append(mat)
    if parent: o.parent = parent
    return o


def gear(r, teeth, depth, mat, loc=(0, 0, 0), rot=(0, 0, 0), parent=None):
    bm = bmesh.new()
    mod = 2 * r / (teeth + 2); root_r = r - 2.25 * mod; pitch = 2 * math.pi / teeth
    prof = []
    for i in range(teeth):
        for off, rr in ((-0.30, root_r), (-0.15, r), (0.15, r), (0.30, root_r)):
            prof.append(((i + off) * pitch, rr))
    hole = root_r * 0.58
    ov = [bm.verts.new((math.cos(a) * rr, math.sin(a) * rr, 0)) for a, rr in prof]
    iv = [bm.verts.new((math.cos(a) * hole, math.sin(a) * hole, 0)) for a, _ in prof]
    for i in range(len(prof)):
        j = (i + 1) % len(prof)
        bm.faces.new((ov[i], ov[j], iv[j], iv[i]))
    me = bpy.data.meshes.new("g"); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new("g", me); bpy.context.collection.objects.link(o)
    o.location = loc; o.rotation_euler = rot; o.data.materials.append(mat)
    sd = o.modifiers.new("s", "SOLIDIFY"); sd.thickness = depth; sd.offset = 0
    bv = o.modifiers.new("b", "BEVEL"); bv.width = depth * 0.12; bv.segments = 2
    if parent: o.parent = parent
    hub = r * 0.2
    cyl(hub, depth * 1.5, (0, 0, 0), mat=mat, parent=o, v=20)
    torus(hole, r * 0.025, (0, 0, 0), mat=mat, parent=o, seg=40, seg2=6)
    for k in range(5):
        a = k * 2 * math.pi / 5 + 0.3
        mid = (hole + hub) / 2
        box(hole - hub, r * 0.09, depth, (math.cos(a) * mid, math.sin(a) * mid, 0), (0, 0, a), mat, o)
    return o


def rock(size, loc, mat, seed):
    rr = random.Random(seed)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=size, location=loc)
    o = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    bm = bmesh.new(); bm.from_mesh(o.data)
    for v in bm.verts:
        v.co *= 1 + rr.uniform(-0.12, 0.12)
    bm.to_mesh(o.data); bm.free()
    o.scale = (rr.uniform(0.6, 1.4), rr.uniform(0.5, 1.2), rr.uniform(0.4, 1.0))
    o.rotation_euler = (rr.uniform(0, 6), rr.uniform(0, 6), rr.uniform(0, 6))
    o.data.materials.append(mat)
    return o


ROMAN = ["XII", "I", "II", "III", "IIII", "V", "VI", "VII", "VIII", "IX", "X", "XI"]


def hand(length, width, ang, mat, root, z=0.0):
    c = Vector((math.cos(ang), math.sin(ang), 0)) * length / 2
    box(length, width, width * 0.6, (c.x, c.y, z), (0, 0, ang), mat, root)
    if width >= 0.04 * length:  # 太い針(時針)は先近くにブレゲ風の丸穴の輪
        e = Vector((math.cos(ang), math.sin(ang), 0)) * length * 0.72
        torus(width * 1.5, width * 0.28, (e.x, e.y, z), (0, 0, 0), mat, root, seg=24, seg2=8)


def clock(Rr, root, gold, num, hour=-0.6, minute=0.5, face=None, ticks=True):
    torus(Rr, Rr * 0.035, mat=gold, parent=root)
    torus(Rr * 1.06, Rr * 0.010, mat=gold, parent=root)
    torus(Rr * 0.80, Rr * 0.012, mat=gold, parent=root)
    torus(Rr * 0.66, Rr * 0.006, mat=gold, parent=root, seg=64, seg2=6)
    if ticks:
        for i in range(60):  # 縁の玉飾り
            b = math.radians(i * 6)
            sphere(Rr * 0.011, (math.cos(b) * Rr, math.sin(b) * Rr, Rr * 0.03), gold, root, seg=6)
    for i in range(12):
        a = math.radians(90 - i * 30)
        text(ROMAN[i], Rr * 0.09, (math.cos(a) * Rr * 0.9, math.sin(a) * Rr * 0.9, 0), (0, 0, a - math.pi / 2),
             num, root, Rr * 0.012)
        if ticks:
            sphere(Rr * 0.022, (math.cos(a) * Rr * 0.66, math.sin(a) * Rr * 0.66, 0), gold, root, seg=6, scale=(1, 1, 0.5))
            for k in range(1, 5):
                b = a - math.radians(6 * k)
                box(Rr * 0.012, Rr * 0.035, Rr * 0.008, (math.cos(b) * Rr * 0.77, math.sin(b) * Rr * 0.77, 0),
                    (0, 0, b), num, root)
    if face:
        cyl(Rr * 0.99, Rr * 0.004, (0, 0, -Rr * 0.01), mat=face, parent=root, v=96)
    hand(Rr * 0.5, Rr * 0.03, hour, gold, root, Rr * 0.02)
    hand(Rr * 0.72, Rr * 0.02, minute, gold, root, Rr * 0.035)
    sphere(Rr * 0.04, (0, 0, Rr * 0.03), gold, root)
    torus(Rr * 0.07, Rr * 0.008, (0, 0, Rr * 0.03), mat=gold, parent=root, seg=24, seg2=6)


def sparkle(loc, size, mat, face_rot):
    e = empty(loc, face_rot)
    sphere(size, (0, 0, 0), mat, e, seg=8, scale=(1, 0.06, 0.06))
    sphere(size, (0, 0, 0), mat, e, seg=8, scale=(0.06, 1, 0.06))
    sphere(size * 0.2, (0, 0, 0), mat, e, seg=8)


def camera(loc, target, lens, roll=0.0):
    cd = bpy.data.cameras.new("c"); cd.lens = lens; cd.clip_end = 2000
    o = bpy.data.objects.new("c", cd); bpy.context.collection.objects.link(o)
    o.location = loc
    q = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y") @ Quaternion((0, 0, 1), roll)
    o.rotation_euler = q.to_euler()
    sc.camera = o
    return o


def area(loc, target, size, energy, color=(1, 1, 1)):
    ld = bpy.data.lights.new("a", "AREA"); ld.energy = energy; ld.size = size; ld.color = color
    o = bpy.data.objects.new("a", ld); bpy.context.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


def point(loc, energy, color=(1, 1, 1), radius=0.3):
    ld = bpy.data.lights.new("p", "POINT"); ld.energy = energy; ld.color = color; ld.shadow_soft_size = radius
    o = bpy.data.objects.new("p", ld); bpy.context.collection.objects.link(o); o.location = loc
    return o


# ---------- Poly Haven(CC0)素材の取り込み・イラスト風の輪郭線 ----------
from mathutils import Matrix
ASSET_DIR = os.path.join(WORKSPACE, "assets", "ph")
_TPL = {}
NOFS = bpy.data.collections.new("nofs"); sc.collection.children.link(NOFS)  # 輪郭線を引かない物(星屑)


def load_asset(name):
    if name in _TPL: return _TPL[name]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=f"{ASSET_DIR}/{name}/{name}_1k.gltf")
    new = [o for o in bpy.data.objects if o not in before]
    bpy.context.view_layer.update()
    meshes = [o for o in new if o.type == "MESH"]
    lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
    for o in meshes:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    ctr = (lo + hi) / 2
    rels = [(o.data, Matrix.Translation(-ctr) @ o.matrix_world.copy()) for o in meshes]
    for o in new:
        o.hide_render = True; o.hide_viewport = True
    _TPL[name] = (rels, max(hi - lo))
    return _TPL[name]


def place(name, loc, rot=(0, 0, 0), size=1.0):
    rels, sz = load_asset(name)
    root = empty(loc, rot, scale=size / sz)
    for data, rel in rels:
        c = bpy.data.objects.new(name, data); bpy.context.collection.objects.link(c)
        c.matrix_basis = rel; c.parent = root
    return root


def dust(r, loc, mat, seg=6):
    o = sphere(r, loc, mat, None, seg=seg)
    for c in list(o.users_collection): c.objects.unlink(o)
    NOFS.objects.link(o)
    return o


def freestyle():
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = "ABSOLUTE"; sc.render.line_thickness = 1.3
    vl = bpy.context.view_layer; vl.use_freestyle = True
    ls = vl.freestyle_settings.linesets.new("L")
    ls.select_silhouette = True; ls.select_crease = True; ls.select_border = True
    ls.select_by_collection = True; ls.collection = NOFS; ls.collection_negation = "EXCLUSIVE"
    ls.linestyle.color = (0.01, 0.02, 0.06); ls.linestyle.thickness = 1.3


# ---------- 素材共通 ----------
GOLD = M("gold", (1.0, 0.64, 0.1), emit=1.0, ecolor=(1.0, 0.56, 0.06), metal=1.0, rough=0.25)
GOLD_BRIGHT = M("goldb", (1.0, 0.68, 0.12), emit=3.2, ecolor=(1.0, 0.6, 0.06), metal=1.0, rough=0.3)
CREAM = M("cream", (1, 0.93, 0.7), emit=8.0)
DARKBLUE = M("darkblue", (0.015, 0.03, 0.16), metal=0.6, rough=0.35)


# ================= シーン1: 螺旋に続く時計トンネル =================
def scene1():
    world(star_scale=500, neb_scale=2.2, base=(0.002, 0.004, 0.02), c1=(0.01, 0.04, 0.4), c2=(0.1, 0.4, 0.9), neb_k=1.0, strength=0.8)
    glass = M("glass", (0.03, 0.1, 0.6), emit=0.6, ecolor=(0.1, 0.3, 1.0), alpha=0.18)
    n = 9
    for i in range(n):
        s = 0.7 ** i
        phi = i * 0.65
        a = 0 if i == 0 else 3.2 * s
        root = empty((math.cos(phi) * a, math.sin(phi) * a, -i * 3.0), (0.40, -0.14, phi * 1.1), scale=s)
        clock(6.4, root, GOLD, GOLD, hour=-0.6 + i * 0.5, minute=0.5 + i * 0.9, face=glass, ticks=(i < 4))
        for q in range(3 if i < 4 else 1):  # 文字盤の内側の小さな歯車
            ga = R.uniform(0, 6.28)
            gear(R.uniform(0.5, 1.1), R.choice((10, 12, 14)), 0.12, M("gear", (1.0, 0.6, 0.1), emit=1.0, ecolor=(1.0, 0.5, 0.06), metal=1.0, rough=0.4),
                 (math.cos(ga) * R.uniform(2.5, 4.2), math.sin(ga) * R.uniform(2.5, 4.2), -0.2), (0, 0, R.uniform(0, 6)), root)
    # 螺旋に沿って流れる暗い青の腕
    for k in range(6):
        cd = bpy.data.curves.new("arm", "CURVE"); cd.dimensions = "3D"; cd.bevel_depth = R.uniform(0.06, 0.14)
        sp = cd.splines.new("BEZIER"); sp.bezier_points.add(5)
        for qi, pnt in enumerate(sp.bezier_points):
            ang = k * 1.05 + qi * 0.9; rad = 7.5 - qi * 1.1
            pnt.co = (math.cos(ang) * rad, math.sin(ang) * rad, -qi * 3.2 - 1)
            pnt.handle_left_type = pnt.handle_right_type = "AUTO"
        ao = bpy.data.objects.new("arm", cd); bpy.context.collection.objects.link(ao); ao.data.materials.append(DARKBLUE)
    # 奥の青い光(球でなく、重ねた薄い光の層)
    for rr in (3, 5, 7, 9, 12):
        sphere(rr, (0.7, 6.3, -34), M("core", (0.2, 0.45, 1), emit=3.0, ecolor=(0.18, 0.42, 1.0), alpha=0.07), None, seg=24)
    point((0.7, 6.3, -26), 30000, (0.4, 0.6, 1.0), 2)
    for k in range(420):
        dust(R.uniform(0.02, 0.07), (R.uniform(-10, 10), R.uniform(-10, 10), R.uniform(-32, 5)), M("d", (1, 1, 1), emit=R.uniform(8, 26)), seg=6)
    camera((-0.3, -5.5, 15), (0.2, 0.3, -9), 36, roll=0.1)


# ================= シーン2: 星空の大時計と歯車 =================
def scene2():
    w = world(star_scale=220, neb_scale=3.0, base=(0.01, 0.015, 0.06), c1=(0.1, 0.1, 0.3), c2=(0.5, 0.35, 0.6), neb_k=0.5)
    nt = w.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = 0.15; mr.inputs["From Max"].default_value = -0.35
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    sky = nt.nodes.new("ShaderNodeBackground"); sky.inputs["Color"].default_value = (1.0, 0.85, 0.6, 1)
    nt.links.new(mr.outputs["Result"], sky.inputs["Strength"])
    old = [l for l in nt.links if l.to_node.type == "OUTPUT_WORLD"][0]
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(old.from_socket, add.inputs[0]); nt.links.new(sky.outputs["Background"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], old.to_socket)
    dark = M("ring", (0.04, 0.05, 0.09), metal=0.8, rough=0.3)
    silver = M("silver", (0.9, 0.92, 1), emit=3.0)
    brass = M("gear", (1.0, 0.6, 0.1), emit=1.4, ecolor=(1.0, 0.5, 0.06), metal=1.0, rough=0.4)
    steel = M("steel", (0.75, 0.78, 0.9), emit=0.5, metal=1.0, rough=0.35)
    root = empty((0, 0, 0), (-0.75, 0.25, 0.35))
    torus(6.2, 0.55, mat=dark, parent=root, seg=96, seg2=16)
    torus(5.4, 0.05, mat=silver, parent=root, seg=96)
    for i in range(60):  # 縁の目盛り
        a = math.radians(i * 6)
        box(0.04, 0.22 if i % 5 == 0 else 0.1, 0.05, (math.cos(a) * 5.7, math.sin(a) * 5.7, 0.58), (0, 0, a - math.pi / 2), silver, root)
    for i in range(12):
        a = math.radians(90 - i * 30)
        text(ROMAN[i], 0.6, (math.cos(a) * 6.2, math.sin(a) * 6.2, 0.58), (0, 0, a - math.pi / 2), silver, root, 0.035)
    for rr, mn in ((4.6, 0.04), (3.4, 0.05), (2.4, 0.04), (1.6, 0.035)):
        torus(rr, mn, (0.3 * (4.6 - rr) / 4.6, 0, 0.15), mat=GOLD_BRIGHT, parent=root, seg=96)
        for k in range(int(rr * 14)):  # 環の目盛り
            a = k / (rr * 14) * 6.2832
            box(0.015, 0.07, 0.03, (math.cos(a) * rr * 0.97 + 0.3 * (4.6 - rr) / 4.6, math.sin(a) * rr * 0.97, 0.15), (0, 0, a - math.pi / 2), GOLD_BRIGHT, root)
    for k, (ax_, ay_) in enumerate(((1.1, 0.2), (0.3, 1.2), (-0.6, 0.8))):  # 傾いた天球環(アストロラーベ風)
        torus(3.8 - k * 0.6, 0.04, (0, 0, 0.35), (ax_, ay_, k * 0.6), GOLD_BRIGHT, root, seg=96)
    for k in range(40):
        a = R.uniform(0, 6.28); rr = R.choice((4.6, 3.4, 2.4, 1.6))
        sphere(R.uniform(0.07, 0.2), (math.cos(a) * rr, math.sin(a) * rr, 0.15), GOLD_BRIGHT, root, seg=10)
    # 噛み合う歯車群(中心距離=ピッチ円の半径の和)
    gl = [(1.7, -1.4, 1.6, 16, brass)]
    chain = [(0, 205, 1.0, 12, steel), (0, 330, 0.85, 11, brass), (1, 250, 0.7, 10, brass), (2, 20, 0.9, 12, steel), (0, 95, 0.6, 9, steel), (3, 300, 0.55, 9, brass)]
    for (pi_, ang, r, z, m_) in chain:
        px, py, pr, pz, _ = gl[pi_]
        dist = (pr - 2 * pr / (pz + 2)) + (r - 2 * r / (z + 2))
        gl.append((px + math.cos(math.radians(ang)) * dist, py + math.sin(math.radians(ang)) * dist, r, z, m_))
    for gi, (gx, gy, gr, tn, gm) in enumerate(gl):
        gear(gr, tn, 0.18, gm, (gx, gy, -0.3 - 0.05 * (gi % 2)), (0, 0, gi * 0.19), root)
    hand(2.6, 0.07, 0.9, GOLD_BRIGHT, root, 0.2); hand(3.8, 0.05, 2.35, GOLD_BRIGHT, root, 0.22)
    sphere(0.22, (0, 0, 0.22), GOLD_BRIGHT, root)
    cyl(5.9, 0.02, (0, 0, -0.35), mat=M("face", (0.01, 0.02, 0.06), emit=0.3, ecolor=(0.1, 0.12, 0.3), alpha=0.5), parent=root, v=96)
    cd = bpy.data.curves.new("rib", "CURVE"); cd.dimensions = "3D"; cd.extrude = 0.9; cd.bevel_depth = 0.08
    sp = cd.splines.new("BEZIER"); sp.bezier_points.add(3)
    pts = [(2.5, 0.5, -5), (4, 1.5, -9), (1, 3.0, -13), (-2.5, 4.0, -17)]
    for pt, c in zip(sp.bezier_points, pts):
        pt.co = c; pt.handle_left_type = pt.handle_right_type = "AUTO"
    ro = bpy.data.objects.new("rib", cd); bpy.context.collection.objects.link(ro)
    ro.data.materials.append(M("rib", (0.03, 0.04, 0.09), metal=0.7, rough=0.3))
    ro.rotation_euler = (0, 0, 0.3)
    for k in range(9):
        sparkle((R.uniform(-6, 6), R.uniform(-3, 4), R.uniform(-1, 7)), R.uniform(0.18, 0.5), CREAM, (1.2, 0, 0.3))
    cloud = M("cloud", (1.0, 0.92, 0.78), emit=1.2, ecolor=(1.0, 0.85, 0.65))
    for k in range(34):  # 下の雲海
        sphere(R.uniform(2, 4.5), (R.uniform(-16, 16), R.uniform(6, 26), R.uniform(-12, -6)), cloud, None, seg=12, scale=(1.8, 1.0, 0.45))
    for k in range(120):
        dust(R.uniform(0.03, 0.07), (R.uniform(-9, 9), R.uniform(-5, 7), R.uniform(-4, 9)), M("d", (1, 0.9, 0.6), emit=20), seg=6)
    area((-4, -8, 6), (0, 0, 0), 8, 400, (0.8, 0.85, 1))
    point((2, -4, -2), 600, (1.0, 0.7, 0.3), 0.5)
    camera((-1.3, -12.5, -5.5), (-0.5, 0, 0.2), 32, roll=0.06)


# ================= シーン3: 時の大聖堂(浮遊する時計と瓦礫) =================
def floor_clock(cx, cy, r, mat, hh=0.5, mm=2.0):
    torus(r, r * 0.03, (cx, cy, 0.03), mat=mat, seg=96, seg2=6)
    torus(r * 0.8, r * 0.015, (cx, cy, 0.03), mat=mat, seg=96, seg2=6)
    for i in range(12):
        a = math.radians(90 - i * 30)
        text(ROMAN[i], r * 0.14, (cx + math.cos(a) * r * 0.9, cy + math.sin(a) * r * 0.9, 0.04), (0, 0, a - math.pi / 2), mat, extr=0.01)
        box(r * 0.02, r * 0.12, 0.02, (cx + math.cos(a) * r * 0.7, cy + math.sin(a) * r * 0.7, 0.03), (0, 0, a - math.pi / 2), mat)
    for k in range(6):
        box(r * 1.6, r * 0.012, 0.02, (cx, cy, 0.03), (0, 0, k * 0.5236), mat)
    for ln, wd, ang in ((r * 0.5, r * 0.05, hh), (r * 0.75, r * 0.035, mm)):
        box(ln, wd, 0.02, (cx + math.cos(ang) * ln / 2, cy + math.sin(ang) * ln / 2, 0.04), (0, 0, ang), mat)


def scene3():
    world(star_scale=80, neb_scale=2, base=(0.004, 0.008, 0.03), c1=(0.02, 0.06, 0.25), c2=(0.1, 0.3, 0.7), neb_k=0.4)
    floor = M("floor", (0.02, 0.025, 0.04), metal=0.6, rough=0.12)
    stone = M("stone", (0.06, 0.05, 0.045), rough=0.8)
    ceil = M("ceil", (0.015, 0.02, 0.04), rough=0.9)
    cyan = M("cyan", (0.6, 0.95, 1.0), emit=6.0, ecolor=(0.55, 0.9, 1.0))
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 40, 0)); bpy.context.active_object.data.materials.append(floor)
    for j in range(14):
        y = 6 + j * 6
        for sx in (-1, 1):
            box(1.6, 1.6, 15, (sx * 9, y, 7.5), mat=stone)
            box(2.2, 2.2, 0.8, (sx * 9, y, 0.4), mat=stone)
            box(2.0, 2.0, 0.5, (sx * 9, y, 14.8), mat=stone)
            torus(4.5, 0.1, (sx * 4.5, y, 14.5), (math.pi / 2, 0, 0), stone, seg=32)
            point((sx * 8, y - 1.5, 1.2), 500, (1.0, 0.6, 0.2), 0.4)
    box(30, 100, 1, (0, 50, 17), mat=ceil)
    box(1, 100, 15, (-14, 50, 7), mat=stone); box(1, 100, 15, (14, 50, 7), mat=stone)
    for rr, mn in ((2.4, 0.05), (3.8, 0.04), (6, 0.06), (9, 0.05), (13, 0.06), (19, 0.06)):
        torus(rr, mn, (0, 7, 0.02), mat=cyan, seg=128, seg2=6)
        torus(rr + 1.1, mn * 0.6, (0, 7, 0.02), mat=cyan, seg=128, seg2=6)
        for k in range(int(rr * 4)):
            a = k / (rr * 4) * 6.28
            text(R.choice("IVXLTMFHNKZYP"), 0.5, (math.cos(a) * (rr + 0.55), 7 + math.sin(a) * (rr + 0.55), 0.03),
                 (0, 0, a - math.pi / 2), cyan, extr=0.01)
        for k in range(int(rr * 7)):  # 外環の刻み
            a = k / (rr * 7) * 6.28
            box(0.04, 0.22, 0.02, (math.cos(a) * (rr + 1.1), 7 + math.sin(a) * (rr + 1.1), 0.03), (0, 0, a - math.pi / 2), cyan)
    for k in range(12):
        a = k * 0.5236
        box(0.05, 5, 0.03, (math.cos(a) * 0.1, 7, 0.025), (0, 0, a), cyan)
    floor_clock(0.0, 3.0, 2.3, cyan, 0.3, 2.2)      # 床の大きな時計盤
    floor_clock(-4.8, 4.5, 1.8, cyan, 1.2, 4.0)
    floor_clock(5.0, 6.5, 1.6, cyan, 2.5, 0.8)
    for k in range(60):
        r = R.uniform(0.3, 1.0) if k > 4 else R.uniform(1.3, 1.8)
        if k <= 4:
            loc = (R.choice((-1, 1)) * R.uniform(3.2, 5.2), R.uniform(3, 14), R.uniform(2.5, 6))
        else:
            loc = (R.uniform(-6.5, 6.5), R.uniform(5, 50), R.uniform(2.5, 13))
        root = empty(loc, (R.uniform(0.9, 1.6), R.uniform(-0.8, 0.8), R.uniform(0, 6.28)))
        torus(r, r * 0.07, mat=GOLD, parent=root, seg=40)
        torus(r * 0.78, r * 0.025, mat=cyan, parent=root, seg=40, seg2=6)
        cyl(r * 0.95, 0.04, (0, 0, -0.02), mat=M("dk", (0.01, 0.02, 0.04), emit=0.12, ecolor=(0.1, 0.4, 0.6)), parent=root, v=40)
        for q in range(6):
            box(r * 1.5, r * 0.025, 0.03, (0, 0, 0.01), (0, 0, q * 0.52), cyan, root)
        hand(r * 0.55, r * 0.05, R.uniform(0, 6), cyan, root, 0.03)
        hand(r * 0.8, r * 0.035, R.uniform(0, 6), cyan, root, 0.04)
    for k in range(190):  # 浮遊する破片(Poly Haven CC0の岩)
        nm = R.choice(["rock_07", "rock_07", "moon_rock_01", "moon_rock_03", "moon_rock_05"])
        place(nm, (R.uniform(-7, 7), R.uniform(3, 50), R.uniform(1.0, 14)),
              (R.uniform(0, 6.28), R.uniform(0, 6.28), R.uniform(0, 6.28)), R.uniform(0.2, 0.9))
    for (x, y, s, rz) in ((0.8, 4.0, 3.2, 0.4), (-2.6, 8.0, 2.4, 2.0), (3.0, 11.0, 2.0, 4.0)):
        o = place("boulder_01", (x, y, s * 0.12), (0, 0, rz), s); o.scale = (o.scale[0] * 1.5, o.scale[1] * 1.2, o.scale[2] * 0.45)
    for (x, y, rz) in ((-6.0, 12, 0.5), (6.2, 18, 2.6), (-6.5, 28, 0.3), (6.5, 36, 2.9)):
        place("gothic_statue", (x, y, 1.6), (0, 0, rz), 3.4)
    cy2 = M("cyan2", (0.6, 0.95, 1.0), emit=7.0, ecolor=(0.55, 0.9, 1.0))
    for k in range(16):
        nm = R.choice(["vintage_pocket_watch", "pocket_watch", "wall_clock"])
        s = R.uniform(0.7, 1.6) if k > 3 else R.uniform(1.4, 2.0)
        loc = (R.choice((-1, 1)) * R.uniform(3.0, 5.0), R.uniform(3, 12), R.uniform(2.2, 5.5)) if k <= 3 else \
            (R.uniform(-6, 6), R.uniform(8, 45), R.uniform(2.5, 12))
        rt = place(nm, loc, (R.uniform(-0.5, 0.5), R.uniform(-0.5, 0.5), R.uniform(-0.6, 0.6)), s)
        torus(0.06, 0.0016, (0, 0, 0), (math.pi / 2, 0, 0), cy2, rt, seg=48, seg2=6)
    for (x, y) in ((-2.4, 2.0), (-0.8, 10), (-1.5, 15), (3.2, 12)):
        bpy.ops.mesh.primitive_cone_add(radius1=0.5, radius2=0.3, depth=1.1, location=(x, y, 0.55), vertices=24)
        bpy.context.active_object.data.materials.append(M("bell", (0.03, 0.04, 0.07), metal=0.8, rough=0.3))
    bpy.ops.mesh.primitive_cone_add(radius1=8, radius2=0.8, depth=40, location=(0, 22, 20), vertices=48)
    bpy.context.active_object.data.materials.append(M("beam", (0.4, 0.7, 1), emit=0.5, ecolor=(0.4, 0.7, 1), alpha=0.07))
    area((0, 20, 15), (0, 20, 0), 14, 3500, (0.45, 0.7, 1.0))
    camera((0, -3.0, 1.1), (0, 26, 4.2), 20, roll=0.0)


# ================= シーン4: 巨大時計と宇宙(宇宙飛行士なし) =================
def scene4():
    world(star_scale=260, neb_scale=2.0, base=(0.01, 0.01, 0.05), c1=(0.12, 0.05, 0.35), c2=(0.4, 0.2, 0.7), neb_k=0.7)
    face = star_mat("face", 6.0, 0.5, (0.012, 0.015, 0.1), (0.12, 0.08, 0.55), (0.6, 0.25, 0.8), 0.7)
    ivory = M("ivory", (1, 0.95, 0.75), emit=5.0, ecolor=(1.0, 0.93, 0.7))
    root = empty((-4.5, 21, 12.5), (math.radians(84), 0, math.radians(-24)))
    rim = M("rim", (1, 0.9, 0.85), emit=1.6, ecolor=(1.0, 0.85, 0.9))
    Rc = 13
    torus(Rc, 1.0, mat=rim, parent=root, seg=128, seg2=24)
    torus(Rc * 0.88, 0.15, mat=GOLD_BRIGHT, parent=root, seg=128)
    torus(Rc * 1.07, 0.55, mat=M('outer', (0.05, 0.06, 0.1), metal=0.8, rough=0.3), parent=root, seg=128, seg2=16)
    torus(Rc * 0.62, 0.08, mat=GOLD_BRIGHT, parent=root, seg=128)
    for i in range(12):
        a = math.radians(90 - i * 30)
        text(ROMAN[i], 1.7, (math.cos(a) * Rc * 0.73, math.sin(a) * Rc * 0.73, 0), (0, 0, a - math.pi / 2), ivory, root, 0.12)
    for i in range(60):  # 目盛り
        a = math.radians(i * 6)
        box(0.08, 0.5 if i % 5 == 0 else 0.25, 0.08, (math.cos(a) * Rc * 0.86, math.sin(a) * Rc * 0.86, 0.05), (0, 0, a - math.pi / 2), ivory, root)
    cyl(Rc, 0.1, (0, 0, -0.5), mat=face, parent=root, v=128)
    for k in range(9):  # 文字盤の惑星
        a = R.uniform(0, 6.28); rr = R.uniform(2.5, 8.5)
        sphere(R.uniform(0.2, 0.55), (math.cos(a) * rr, math.sin(a) * rr, -0.2), M("pl", (0.4, 0.6, 1), emit=R.uniform(2, 5), ecolor=R.choice([(0.4, 0.6, 1.0), (1.0, 0.5, 0.8), (0.7, 0.5, 1.0)])), root, seg=14)
    pts = [(R.uniform(-9, 9), R.uniform(-9, 9)) for _ in range(14)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):  # 星座線
        if (x0 - x1) ** 2 + (y0 - y1) ** 2 < 70 and x0 * x0 + y0 * y0 < 110 and x1 * x1 + y1 * y1 < 110:
            ang = math.atan2(y1 - y0, x1 - x0); ln = math.hypot(x1 - x0, y1 - y0)
            box(ln, 0.03, 0.02, ((x0 + x1) / 2, (y0 + y1) / 2, -0.3), (0, 0, ang), M("cl", (0.7, 0.8, 1), emit=6), root)
    hand(6.5, 0.5, math.radians(88), ivory, root, 0.2); hand(4.8, 0.6, math.radians(125), ivory, root, 0.3)
    sphere(0.8, (0, 0, 0.3), ivory, root)
    dk = M("mach", (0.02, 0.03, 0.05), metal=0.7, rough=0.4)
    red = M("red", (1, 0.1, 0.2), emit=14.0); teal = M("teal", (0.2, 0.9, 1), emit=10.0)
    box(14, 2, 28, (9.5, 26, 11), mat=dk)
    for k in range(70):
        x = R.uniform(2.5, 11.5); y = 24.5 - R.uniform(0, 3); z = R.uniform(-0.5, 20)
        w, d, h = R.uniform(0.8, 2.4), R.uniform(0.6, 2.0), R.uniform(0.8, 3)
        box(w, d, h, (x, y, z), mat=dk)
        for q in range(R.randint(0, 3)):
            box(0.4, 0.05, 0.2, (x + R.uniform(-w / 3, w / 3), y - d / 2 - 0.02, z + R.uniform(-h / 3, h / 3)), mat=R.choice([red, teal]))
    for k in range(14):  # パイプと配線
        px = R.uniform(2.5, 11.5)
        cyl(R.uniform(0.12, 0.3), 24, (px, 23.3 - R.uniform(0, 1.5), 9), mat=dk, v=14)
        for q in range(6):
            torus(0.3, 0.03, (px, 23.0, R.uniform(0, 20)), (math.pi / 2, 0, 0), teal, seg=20, seg2=6)
    pink = M("pk", (1, 0.7, 0.9), emit=3.0, ecolor=(1, 0.65, 0.9))
    for k in range(8):
        box(30, 1.2, 0.15 + k * 0.03, (0, -1.5 + k * 1.6, 0.06), mat=M("st", (0.02, 0.03, 0.05), metal=0.5, rough=0.25))
        box(30, 0.04, 0.03, (0, -0.9 + k * 1.6, 0.17), mat=teal if k % 2 else pink)
    box(120, 3, 0.1, (0, 40, 0.02), mat=M("hz", (1, 0.75, 0.95), emit=9.0, ecolor=(1, 0.7, 0.95)))
    for k in range(26):  # 浮遊する破片
        place(R.choice(["moon_rock_01", "moon_rock_03", "moon_rock_05"]), (R.uniform(-6, 6), R.uniform(2, 16), R.uniform(0.5, 13)),
              (R.uniform(0, 6.28), R.uniform(0, 6.28), R.uniform(0, 6.28)), R.uniform(0.15, 0.6))
    for k in range(160):
        dust(R.uniform(0.02, 0.07), (R.uniform(-6, 6), R.uniform(2, 14), R.uniform(0, 12)), M("d", (0.7, 0.8, 1), emit=18), seg=6)
    area((-1, -6, 4), (0, 0, 1), 6, 500, (1.0, 0.7, 0.95))
    camera((0, -8.5, 1.3), (0.4, 0, 5.5), 28, roll=0.0)


{1: scene1, 2: scene2, 3: scene3, 4: scene4}[SID]()

if os.environ.get("TOON", "1") == "1":
    freestyle()
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True; sc.cycles.denoiser = "OPENIMAGEDENOISE"
sc.cycles.max_bounces = 4; sc.cycles.use_adaptive_sampling = True
sc.render.resolution_x, sc.render.resolution_y = RES; sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"; sc.render.filepath = OUT
try:
    sc.view_settings.view_transform = "AgX"
except TypeError:
    pass
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
bpy.ops.render.render(write_still=True)
print("DONE", OUT)
