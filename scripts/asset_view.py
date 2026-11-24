"""assets/ph/*/*.gltf を取り込み、寸法をログに出して3方向から描く。"""
import bpy, glob, os, math, sys
from mathutils import Vector
OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)
for path in sorted(glob.glob("assets/ph/*/*.gltf")):
    name = os.path.basename(os.path.dirname(path))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=path)
    ms = [o for o in bpy.data.objects if o.type == "MESH"]
    lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
    for o in ms:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    dim = hi - lo; ctr = (hi + lo) / 2
    print("DIM", name, [round(x, 3) for x in dim], "meshes", len(ms), "polys", sum(len(o.data.polygons) for o in ms))
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.55, 0.65, 1)
    sd = bpy.data.lights.new("s", "SUN"); sd.energy = 4
    so = bpy.data.objects.new("s", sd); bpy.context.collection.objects.link(so); so.rotation_euler = (0.8, 0.2, 0.6)
    r = max(dim) * 1.6 + 0.01
    for tag, off in (("front", (0, -1, 0)), ("top", (0, -0.01, 1)), ("side", (1, 0, 0.2))):
        cd = bpy.data.cameras.new("c"); cd.lens = 50
        co = bpy.data.objects.new("c", cd); bpy.context.collection.objects.link(co); sc.camera = co
        co.location = ctr + Vector(off).normalized() * r * 1.6
        co.rotation_euler = (ctr - co.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.engine = "CYCLES"; sc.cycles.samples = 8; sc.cycles.use_denoising = False
        sc.render.resolution_x = sc.render.resolution_y = 300
        sc.render.filepath = f"{OUT}/{name}_{tag}.png"; bpy.ops.render.render(write_still=True)
