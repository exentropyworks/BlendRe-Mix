"""BGE-Remix P11: the test scenes (run inside our Blender, background).

Each track makes its own scenes in its own module, each with make(folder, E):
  p11a_scenes  Part A: physics and motion in Remix's picture (A2-A5)

What each track expects is written into E under its own keys; a track whose
scenes failed is named in E["failed"]. All of it goes to p11_expected.json.

argv (after --): folder
"""

import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # the tracks' scene modules
for phase in ("p9", "p6", "p3", "p2"):
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), phase))

TRACKS = ("p11a",)


def main():
    import importlib
    argv = sys.argv[sys.argv.index("--") + 1:]
    folder = argv[0]
    os.makedirs(folder, exist_ok=True)
    E = {"failed": {}}
    for track in TRACKS:
        try:
            importlib.import_module(track + "_scenes").make(folder, E)
        except Exception:
            E["failed"][track] = traceback.format_exc()
            print("BGE-Remix: making the %s scenes failed:\n%s" % (track, E["failed"][track]))
    with open(os.path.join(folder, "p11_expected.json"), "w") as f:
        json.dump(E, f, indent=1)
    print("BGE-Remix: wrote", os.path.join(folder, "p11_expected.json"))


if __name__ == "__main__":
    main()
