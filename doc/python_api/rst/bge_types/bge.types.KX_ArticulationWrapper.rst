KX_ArticulationWrapper(PyObjectPlus)
====================================

.. module:: bge.types

base class --- :class:`PyObjectPlus`

.. class:: KX_ArticulationWrapper(PyObjectPlus)

   BGE-Remix P11 (PhysX only): an articulation, from
   :func:`bge.constraints.getArticulation`. It follows its root: after a body
   or joint of it is removed the articulation is built again, and the wrapper
   gives the new one (or raises RuntimeError when there is none any more).

   A joint's axes are numbered as the 6DOF joint's: 0, 1, 2 sliding along the
   joint's X, Y, Z; 3, 4, 5 turning about them (a Hinge turns about its X: 3).
   Left out (-1), the joint's first moving axis. Angles are in radians, and
   are the constraint's target's against the object it is on, as the Rigid
   Body Joint's limits (and Bullet's).

   A link is given as its object or its index in :data:`links`.

   .. attribute:: root

      The root object. (read-only)

      :type: :class:`KX_GameObject`

   .. attribute:: fixed

      The root is fixed to the world (a robot arm); False: it moves freely (a
      ragdoll). (read-only)

      :type: boolean

   .. attribute:: links

      The links, the root first, each after its parent. (read-only)

      :type: list of :class:`KX_GameObject`

   .. attribute:: joints

      Each link's joint to its parent (its constraint id; 0 for the root).
      (read-only)

      :type: list of int

   .. attribute:: parents

      Each link's parent, as an index in :data:`links` (-1 for the root).
      (read-only)

      :type: list of int

   .. attribute:: ordinaryJoints

      The joints of its bodies left as ordinary joints: one that would close a
      loop, a kind an articulation has no joint for, one to the world or to an
      object outside it. (read-only)

      :type: list of int

   .. attribute:: ragdoll

      A ragdoll's articulation (Make Ragdoll): True lets its capsules go, they
      fall from where the bones hold them, at the speed the bones move them,
      and the bones follow them; False puts them back on the bones, which
      their animation moves again. None for an articulation that is not a
      ragdoll's. While the capsules are on the bones, the other attributes and
      methods raise RuntimeError.

      :type: boolean

   .. method:: getJointPosition(link, axis=-1)

      The position of the link's joint to its parent on one axis.

      :rtype: float

   .. method:: getJointSpeed(link, axis=-1)

      The speed of the link's joint on one axis (a second).

      :rtype: float

   .. method:: setJointTarget(link, target, axis=-1, stiffness=1000.0, damping=100.0, maxForce=0.0)

      Drives the joint to a position, like a spring; maxForce 0: no limit.
      Stiffness and damping 0 turn the drive off.

   .. method:: setJointSpeed(link, speed, axis=-1, maxForce=0.0)

      Turns (or slides) the joint at a speed, like a motor, with at most
      maxForce (0: no limit).
