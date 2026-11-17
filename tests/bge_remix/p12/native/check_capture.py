"""BGE-Remix P12: the capture reader's output (p12_usd_check's dump) against
what capture_writer.py wrote (its expected.json), in the capture's own space
(the room: metres, Z up). Exit code: the number of failed checks.

  python check_capture.py <expected.json> <dump.json>
"""

import json
import sys


def near(a, b, tol=1e-4):
    if isinstance(a, list):
        return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))
    return a is not None and abs(a - b) <= tol


def main(argv):
    E = json.load(open(argv[0]))
    D = json.load(open(argv[1]))
    failed = 0

    def check(name, ok):
        nonlocal failed
        print("%s  %s" % ("ok   " if ok else "FAIL ", name))
        failed += 0 if ok else 1

    check("read (%s)" % D.get("error", "no error"), "error" not in D)
    if "error" in D:
        return failed
    check("units 1 m, Z up", D["meters_per_unit"] == 1 and D["z_up"] == 1)
    check("nothing left out (%r)" % D["report"], D["report"] == "")
    check("%d meshes (want %d)" % (len(D["meshes"]), len(E["meshes"])), len(D["meshes"]) == len(E["meshes"]))
    for m in D["meshes"]:
        want = E["meshes"].get(m["hash"])
        check("mesh %s: %d vertices, %d faces" % (m["hash"], m["vertices"], m["faces"]),
              bool(want) and m["vertices"] == want["vertices"] and m["faces"] == want["triangles"] and
              m["normals"] == 1 and m["uvs"] == 1)
    check("%d instances (want %d)" % (len(D["instances"]), len(E["objects"])),
          len(D["instances"]) == len(E["objects"]))
    by_name = {i["name"]: i for i in D["instances"]}
    worst = 0.0
    for o in E["objects"]:
        i = by_name.get(o["name"])
        ok = bool(i) and i["mesh"] == o["mesh"] and i["material"] == o["material"]
        if i:
            # USD's row vectors: the transpose of Blender's matrix
            usd = [[i["matrix"][c * 4 + r] for c in range(4)] for r in range(4)]
            worst = max(worst, max(abs(usd[r][c] - o["matrix"][r][c]) for r in range(4) for c in range(4)))
        check("instance %s: its mesh and material" % o["name"], ok)
    check("every place as written (worst %.2g)" % worst, worst <= 1e-5)
    mats = {m["hash"]: m for m in D["materials"]}
    for h, want in E["materials"].items():
        m = mats.get(h)
        ok = bool(m) and m["sub_identifier"] == want["mdl"]
        for name, v in want["inputs"].items():
            got = (m or {}).get("inputs", {}).get(name)
            if got is None:
                ok = False
            elif isinstance(v, list):
                ok = ok and near(got["v"][:len(v)], v)
            elif isinstance(v, bool):
                ok = ok and got["v"][0] == (1 if v else 0)
            else:
                ok = ok and near(got["v"][0], v)
        if want["texture"]:
            tex = (m or {}).get("inputs", {}).get("diffuse_texture") or {}
            ok = ok and tex.get("exists") == 1 and tex.get("path", "").endswith(h + ".dds")
        check("material %s (%s): its inputs" % (h, want["key"]), ok)
    lights = {l["hash"]: l for l in D["lights"]}
    for want in E["lamps"]:
        l = lights.get(want["hash"])
        ok = bool(l) and l["kind"] == 0 and near(l["intensity"], want["intensity"]) and \
            near(l["radius"], want["radius"]) and near(l["color"], want["colour"])
        if want["cone"] is not None:
            ok = ok and l["shaped"] == 1 and near(l["cone_angle"], want["cone"]) and \
                near(l["cone_softness"], want["softness"])
        check("light %s (%s)" % (want["hash"], want["name"]), ok)
    cam = D.get("camera") or {}
    check("the camera", near(cam.get("focal_length"), E["camera"]["focal_length"]) and
          near(cam.get("horizontal_aperture"), E["camera"]["horizontal_aperture"]))
    print("%d failed" % failed)
    return failed


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
