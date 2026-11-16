KX_DestructibleWrapper(PyObjectPlus)
====================================

.. module:: bge.types

base class --- :class:`PyObjectPlus`

.. class:: KX_DestructibleWrapper(PyObjectPlus)

   BGE-Remix P11 (PhysX only): a destructible (Make Destructible), from
   :func:`bge.constraints.getDestructible`. Its pieces are game objects; the
   ones NVIDIA Blast holds together move as one body (a group). A piece's
   speed can be read, and forces and impulses act on its group; setting a
   piece's position or speed has no effect while it is a piece.

   The wrapper finds the destructible again from any of its pieces still in
   the game; when none is left it raises RuntimeError.

   .. attribute:: root

      The parent piece (Make Destructible's largest), or None once it is gone.
      (read-only)

      :type: :class:`KX_GameObject`

   .. attribute:: pieces

      Every piece still in the game. (read-only)

      :type: list of :class:`KX_GameObject`

   .. attribute:: brokenOff

      The pieces broken off (not in what is still held, or the largest part).
      The Destruction Budget (World > Physics) removes the oldest of these
      across the scene. (read-only)

      :type: list of :class:`KX_GameObject`

   .. attribute:: groups

      How many groups the pieces are in (1: whole). (read-only)

      :type: integer

   .. attribute:: broken

      True once a bond broke. (read-only)

      :type: boolean

   .. attribute:: bonds

      Its bonds: where its pieces touch, and, with an anchored base, where its
      bottom pieces rest on the ground. (read-only)

      :type: integer

   .. attribute:: bondsBroken

      (read-only)

      :type: integer

   .. attribute:: anchored

      Its bottom pieces are held by the ground. (read-only)

      :type: boolean

   .. attribute:: strength

      The impulse (N s) a hit needs to break it where it lands.

      :type: float

   .. method:: damage(point, radius=1.0, amount=1.0)

      Damage around a point (world coordinates): a bond at the point takes the
      amount (1 breaks it), less towards the radius.

      :arg point: Where.
      :type point: 3D vector
      :arg radius: How far it reaches (m).
      :type radius: float
      :arg amount: The damage at the point.
      :type amount: float
