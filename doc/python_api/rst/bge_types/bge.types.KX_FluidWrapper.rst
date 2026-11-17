KX_FluidWrapper(PyObjectPlus)
=============================

.. module:: bge.types

base class --- :class:`PyObjectPlus`

.. class:: KX_FluidWrapper(PyObjectPlus)

   BGE-Remix P11 (PhysX only): a fluid volume (Make Fluid Volume), from
   :func:`bge.constraints.getFluid`. Things float in it by their mass and
   size, are slowed by its drag and carried along by its current. When its
   object has been ended the wrapper raises RuntimeError.

   .. attribute:: volume

      The volume's object. (read-only)

      :type: :class:`KX_GameObject`

   .. attribute:: type

      "WATER" or "LAVA". (read-only)

      :type: string

   .. attribute:: density

      How much the fluid weighs (kg/m\ :sup:`3`): what is lighter than the
      fluid it pushes aside floats. (read-only)

      :type: float

   .. attribute:: drag

      How quickly things in it slow down, moving and turning (per second,
      when wholly under; less the less of them is under). (read-only)

      :type: float

   .. attribute:: current

      Its flow (m/s), along the volume's own axes: things in it are carried
      towards that speed.

      :type: :class:`mathutils.Vector`

   .. attribute:: splashes

      Whether something going in fast makes a splash. (read-only)

      :type: boolean

   .. attribute:: objects

      The objects in it now (a destructible's pieces each). (read-only)

      :type: list of :class:`KX_GameObject`

   .. method:: submerged(gameobj)

      How much of the object is under the volume's surface: 0 (out of it) to
      1 (wholly under). A character is measured where it stands (it is not
      pushed: swimming is the game's own logic).

      :arg gameobj: Any object.
      :type gameobj: :class:`KX_GameObject`
      :return: 0 to 1.
      :rtype: float
