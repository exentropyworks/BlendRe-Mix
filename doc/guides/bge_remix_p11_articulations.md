# BGE-Remix P11: articulations and ragdolls (PhysX)

An articulation is a tree of bodies joined by Rigid Body Joints that PhysX
solves as one thing. Its joints never drift apart, whatever the masses: a
heavy ball on a light chain, a long rope, a robot arm. Ordinary joints pull
bodies back together after each step and stretch when the masses differ a
lot; articulation joints do not.

Articulations need PhysX (World > Physics > Engine: PhysX, CPU or GPU).
Under Bullet, and in stock Blender 2.79b, the same file runs with ordinary
joints.

## Making one

1. Join the bodies with Rigid Body Joint constraints as usual (Ball, Hinge,
   Cone Twist, Generic 6DOF).
2. On one of them, the Physics tab's Articulation panel: Root.
   - Moves Freely: a ragdoll, a vehicle's suspension, anything loose.
   - Fixed to the World: a robot arm, a hanging chain, a door on its post.

At the first physics step the root and every body joined to it, through any
number of joints, become one articulation.

Which joints it can take:

| Joint | In an articulation |
|---|---|
| Ball | turns freely about every axis |
| Hinge | turns about its X, within its limits |
| Cone Twist | twist and both swings within their limits (the swings' limit is a box, not Bullet's cone) |
| Generic 6DOF | all locked (fixed), one sliding axis, only the twist, or turning only |
| Angular | none (it lets the bodies move apart) |

A joint it cannot take stays an ordinary joint beside it: one that would
close a loop (an articulation is a tree), a Generic 6DOF sliding on two axes
or sliding and turning, a joint to the world or to a body that does not move,
or to another articulation, a character or a soft body.

Things to know:

- Bodies joined in an articulation never collide with the body they are
  joined to (PhysX), whatever the joint's Disable Linked Collision says.
  Other links of it do collide.
- Moving it: set the root's position (it moves the whole articulation), or
  the root's speed when it moves freely. The other links follow their
  joints; setting their position or speed has no effect (the console says
  so once). Forces and impulses work on any link.
- Removing a body or a joint of it, adding a joint to it, or parenting one
  of its bodies takes the articulation apart; what is left is built again at
  the next step.
- The 6DOF joints' motors and springs drive the articulation's joints.

## From Python

    import bge
    art = bge.constraints.getArticulation(own)   # None: not in one
    art.links, art.joints, art.parents, art.ordinaryJoints, art.root, art.fixed
    art.getJointPosition(door)                   # radians (or distance)
    art.getJointSpeed(door)
    art.setJointTarget(arm, math.radians(30))    # to a position, like a spring
    art.setJointSpeed(door, -1.0, maxForce=500)  # at a speed, like a motor

A link is its object or its index in `links`. Axes: 0-2 slide along the
joint's X, Y, Z; 3-5 turn about them; left out, the joint's first moving
axis. A joint's angles, limits and speeds are those of the constraint's
target against the object it is on, as Bullet's and P6's (a door's hinge on
the door: the post's turn against the door, the door's own turned over). Logic bricks for this come later, with the brick review.

## Ragdolls

Make Ragdoll (the Object menu, or an armature's Physics tab) puts a capsule
on each bone (Thickness: the radius as a part of the bone's length; Mass in
all, shared by size), joins each to its parent bone's capsule with a Cone
Twist joint, and makes the top one the root (Moves Freely). A bone's IK
limits (Bone > Inverse Kinematics), where set, give its joint's twist (Y) and
swing (X, Z); the others take Swing and Twist. The capsules are invisible in
the game and drawn as wire in the editor; each is parented to its bone and
sits on the armature's layers (objects on a hidden layer are not in the
game). Making it again replaces them.

In the game the capsules follow the bones until a script lets them go:

    rag = bge.constraints.getArticulation(armature)
    rag.ragdoll = True     # falls from its pose, at the bones' speed; the bones on the capsules
    rag.ragdoll = False    # back on the bones, animated again

Capsules of bones beside each other (two thighs) must not overlap at rest, or
they push apart when let go: lower the Thickness.

## In the Remix View

The physics layer shows each joint's state in its colour:

| Colour | Check mode | Run |
|---|---|---|
| Red | a joint of an articulation's body it cannot take (the warning says why) | the same |
| Black | in no articulation, in a scene that has some | the same |
| White | in an articulation, ready | at rest |
| Green | | moving |
| Yellow | | at one of its limits |
| Blue | | driven (a motor, a spring, a target or a speed set) |

Notes: a root with nothing joined to it; an articulation root under Bullet;
two bodies on an ordinary joint with masses more than ten times apart
(an articulation would hold them).
