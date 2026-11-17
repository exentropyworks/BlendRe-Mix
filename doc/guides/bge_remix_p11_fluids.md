# BGE-Remix P11: game fluids (water and lava)

A fluid volume is water or lava that things float in, sink in, are slowed
by and are carried along by. It is a volume with forces, not a liquid: it
does not pour, fill or flow, and its surface is flat for physics (the waves
are in the picture).

Floating needs PhysX (World > Physics > Engine: PhysX). Under Bullet, and in
stock Blender 2.79b, the same file plays and things fall through the volume.

## Making one

Select a mesh, then Object > Make Fluid Volume (or the Physics tab's Fluid
Volume panel):

- **Type**: Water or Lava. It sets the density and drag below.
- **Density**: how much the fluid weighs. Water is 1000 kg/m³, lava 3100.
- **Drag**: how quickly things in it slow down, moving and turning: water 3,
  lava 24 (per second, when wholly under).
- **Current**: its flow in m/s, along the object's own axes, so turning the
  volume turns its current. Things in it are carried towards that speed.
- **Splashes**: a splash where something goes in fast.

The volume's shape is the mesh's convex hull, and its surface is the top of
it. A box makes a pool or a lake; a long box with a current makes a river.

The object becomes a static Ghost with Convex Hull bounds. Things pass
through it, so a Collision sensor on the volume sees what goes in.

If the mesh has no material, it gets the Water or the Lava preset, made a
flipbook so it moves in Remix. A mesh without a UV map gets one projected
from above (a UV unit a metre). A material you have set is kept.

Make Fluid Volume on a volume again changes its settings.

## Floating and sinking

Things float or sink by their real mass and size. A thing floats when it is
lighter than the fluid it pushes aside:

- A 1 m crate of 300 kg floats with about a third under water.
- One of 2000 kg sinks in water. One of 1500 kg sinks in water but floats in
  lava, about half under.
- Blender's default (1 kg on a 2 m cube) floats almost on top of the water.
  Set the Mass in the Physics tab.

Each part of a thing pushes up where it is under the surface, so things bob,
settle at the right depth and turn upright as real ones do: a plank lies
flat, a raft levels out. What floating does to a thing's speed is shared
with the water it moves (its added mass), so a light ball dropped in does
not leap far out again.

Moving rigid and dynamic bodies are pushed, and a destructible's broken-off
pieces float like anything else. Characters are not pushed (swimming is the
game's own logic), nor static objects, soft bodies or cloth.

**Lava** works the same way with its own numbers: it holds things higher,
pushes them up harder and stops them sooner. It does nothing else to them;
scripts can ask what is in it and how deep, and do their own burning.

## Splashes

When a body goes in faster than about 1 m/s, a short burst goes up where it
crossed the surface: bigger for bigger and faster bodies, white spray for
water, glowing orange for lava. Remix draws it with its GPU particles; the
game's own picture draws the same splash. There are at most 8 splashes at a
time, and a body splashes again only after half a second.

In Remix the particles are lit surfaces in their material (P8's known
difference): water's spray shows best in daylight.

## The Lava preset

Material > RTX Remix Preset > Lava: plates of dark crust with glowing cracks
between them. It moves slowly as a flipbook, made like Water's (2 frames a
second, an 8 s loop). It is emissive, so in Remix it lights what is near it.
The game's OpenGL draws it still, as it draws Water.

## From Python

    import bge
    v = bge.constraints.getFluid(pool)   # None: not one, or not PhysX
    v.type, v.density, v.drag, v.splashes, v.volume
    v.current = (0.5, 0.0, 0.0)          # m/s, along the volume's own axes
    for ob in v.objects:                  # what is in it now
        print(ob.name, v.submerged(ob))   # 0 out, 1 wholly under

A logic brick comes later, with the brick review. A Collision sensor on the
volume already sees what goes in.

Volumes are made from what is in the scene when the game starts.

## In the Remix View

The physics layer shows each volume's outline and, if it has a current,
arrows on its surface. Its info line gives the type, density, drag and
current. Under Bullet a note says that floating needs PhysX.

Run, in your colours:

| Colour | The volume | An object in a volume |
|---|---|---|
| White | nothing in it | |
| Green | something in it | it floats |
| Blue | a splash just now | |
| Yellow | | it sinks |

A destructible breaking keeps its own colours while it breaks.
