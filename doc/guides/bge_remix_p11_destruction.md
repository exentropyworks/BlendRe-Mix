# BGE-Remix P11: destruction (PhysX with NVIDIA Blast)

A destructible is an object cut into pieces that the game breaks apart:
where a hard hit lands, where an explosion goes off, and where the weight on
an anchored base is too much. The pieces NVIDIA Blast still holds together
move as one body; when Blast splits them, each new part becomes its own body
and keeps the speed it had there.

Breaking needs PhysX (World > Physics > Engine: PhysX). Under Bullet, and in
stock Blender 2.79b, the same file plays the destructible as one whole object
that never breaks.

## Making one

Select a mesh, then Object > Make Destructible (or the Physics tab's
Destruction panel):

- **Pieces**: how many pieces Blender's Cell Fracture cuts it into (about:
  empty cells are left out).
- **Seed**: the same seed always gives the same pieces.
- **Strength**: the impulse (N s) a hit needs to break it where it lands.
  A 20 kg ball at 10 m/s gives about 200 N s; less only damages it, and
  damage adds up.
- **Mass**: in all, shared between the pieces by their volume.
- **Anchored Base**: its bottom pieces are held by the ground, as a wall's or
  a building's. What is still joined to them stays where it is; what is not
  falls.

The pieces are one compound rigid body: the largest is the parent, the
others its children. The original mesh moves to layer 20, kept for making it
again: Make Destructible on any piece replaces the pieces (with the options
you give it). With several meshes selected (pieces you cut yourself), those
are the pieces.

## In the game

- **Impacts**: a hit over the Strength breaks the bonds where it lands.
- **Explosions**: `bge.constraints.explode(point, radius, damage)` breaks
  every destructible within the radius (damage 1 breaks a bond at the point,
  less towards the radius) and throws what breaks loose out from the point.
  A logic brick comes later, with the brick review.
- **Collapse**: an anchored destructible's weight loads its bonds down to the
  ground (Blast's stress solver); a bond that carries far too much breaks. A
  part left joined to nothing falls.

The **Destruction Budget** (World > Physics) keeps a scene playable: Max
Pieces is the most broken-off pieces in the scene (500 at first; 0 no
limit); over it, the oldest broken-off pieces are removed. Debris Lifetime
removes them after that many seconds (0: kept until the budget needs room).

## From Python

    import bge
    d = bge.constraints.getDestructible(piece)   # None: not one, or not PhysX
    d.pieces, d.brokenOff, d.groups, d.broken, d.bonds, d.bondsBroken
    d.anchored, d.strength, d.root
    d.damage((0, 0, 1), radius=0.5, amount=1.0)
    bge.constraints.explode(own.worldPosition, 2.0, 4.0)

While an object is a piece its position and speed are its group's: setting
them has no effect; forces and impulses act on its group.

Destructibles are made from what is in the scene when the game starts (not
from objects added later).

## In the Remix View

The physics layer shows each destructible's parent piece with its pieces
counted, its Strength, and whether its base is anchored. A note appears when
the scene's destructibles, all broken, would go over Max Pieces, and under
Bullet that breaking needs PhysX.

Run, in your colours:

| Colour | Run |
|---|---|
| White | whole, or at rest |
| Green | breaking (it split in the last moments) |
| Blue | damaged by a script just now (no bond broke) |
| Yellow | at the Destruction Budget: it has taken broken-off pieces of it |
