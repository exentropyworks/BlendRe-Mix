
Physics Constraints (bge.constraints)
=====================================

.. module:: bge.constraints


Examples
--------

.. include:: __/examples/bge.constraints.py
   :start-line: 1
   :end-line: 4

.. literalinclude:: __/examples/bge.constraints.py
   :lines: 6-


Functions
---------

.. function:: createConstraint( \
      physicsid_1, physicsid_2, constraint_type, \
      pivot_x=0.0, pivot_y=0.0, pivot_z=0.0, \
      axis_x=0.0, axis_y=0.0, axis_z=0.0, flag=0)

   Creates a constraint.

   :arg physicsid_1: The physics id of the first object in constraint.
   :type physicsid_1: int

   :arg physicsid_2: The physics id of the second object in constraint.
   :type physicsid_2: int

   :arg constraint_type: The type of the constraint, see `Create Constraint Constants`_.

   :type constraint_type: int

   :arg pivot_x: Pivot X position. (optional)
   :type pivot_x: float

   :arg pivot_y: Pivot Y position. (optional)
   :type pivot_y: float

   :arg pivot_z: Pivot Z position. (optional)
   :type pivot_z: float

   :arg axis_x: X axis angle in degrees. (optional)
   :type axis_x: float

   :arg axis_y: Y axis angle in degrees. (optional)
   :type axis_y: float

   :arg axis_z: Z axis angle in degrees. (optional)
   :type axis_z: float

   :arg flag: 128 to disable collision between linked bodies. (optional)
   :type flag: int

   :return: A constraint wrapper.
   :rtype: :class:`~bge.types.KX_ConstraintWrapper`

.. function:: exportBulletFile(filename)

   Exports a file representing the dynamics world (usually using ``.bullet`` extension).

   See `Bullet binary serialization <http://bulletphysics.org/mediawiki-1.5.8/index.php/Bullet_binary_serialization>`__.

   :arg filename: File path.
   :type filename: str

.. function:: getAppliedImpulse(constraintId)

   :arg constraintId: The id of the constraint.
   :type constraintId: int

   :return: The most recent applied impulse.
   :rtype: float

.. function:: getVehicleConstraint(constraintId)

   :arg constraintId: The id of the vehicle constraint.
   :type constraintId: int

   :return: A vehicle constraint object.
   :rtype: :class:`~bge.types.KX_VehicleWrapper`

.. function:: getArticulation(gameobj)

   BGE-Remix P11 (PhysX only): the articulation the object is a link of. An
   object whose Physics tab sets it as an Articulation Root, and the bodies
   joined to it by Rigid Body Joints, are solved by PhysX as one
   articulation (built at the first physics step, built again when a body or
   joint of it is added or removed).

   An armature with a ragdoll (Make Ragdoll) gives its ragdoll's articulation,
   whether its capsules are let go or still on the bones: its ``ragdoll``
   attribute switches between the two.

   :arg gameobj: Any link of the articulation (its root or another body), or a
      ragdoll's armature.
   :type gameobj: :class:`~bge.types.KX_GameObject`

   :return: The articulation, or None (not PhysX, or the object is in none).
   :rtype: :class:`~bge.types.KX_ArticulationWrapper`

.. function:: getDestructible(gameobj)

   BGE-Remix P11: the destructible the object is a piece of. Make Destructible
   (the Object menu, or the Physics tab's Destruction panel) cuts a mesh into
   pieces; under PhysX the game breaks them apart with NVIDIA Blast. Under
   Bullet a destructible plays as one whole object, and this gives None.

   :arg gameobj: Any piece of the destructible.
   :type gameobj: :class:`~bge.types.KX_GameObject`

   :return: The destructible, or None (not PhysX, or the object is no piece).
   :rtype: :class:`~bge.types.KX_DestructibleWrapper`

.. function:: explode(point, radius=1.0, damage=1.0)

   BGE-Remix P11 (PhysX only): breaks every destructible within the radius:
   a bond at the point takes the damage, less towards the radius (1 breaks
   it). What breaks loose is thrown out from the point (1 m/s for each unit
   of damage there, less further out).

   :arg point: Where (world coordinates).
   :type point: 3D vector
   :arg radius: How far it reaches (m).
   :type radius: float
   :arg damage: The damage at the point (1 breaks a bond).
   :type damage: float
   :return: How many destructibles it hit.
   :rtype: int

.. function:: getFluid(gameobj)

   BGE-Remix P11: the fluid volume the object is. Make Fluid Volume (the
   Object menu, or the Physics tab's Fluid Volume panel) makes a mesh water
   or lava; under PhysX things float in it by their mass and size, are slowed
   by it and carried along by its current. Under Bullet things fall through
   it, and this gives None.

   :arg gameobj: The volume's object.
   :type gameobj: :class:`~bge.types.KX_GameObject`

   :return: The volume, or None (not PhysX, or the object is no volume).
   :rtype: :class:`~bge.types.KX_FluidWrapper`

.. function:: getCharacter(gameobj)

   :arg gameobj: The game object with the character physics.
   :type gameobj: :class:`~bge.types.KX_GameObject`

   :return: Character wrapper.
   :rtype: :class:`~bge.types.KX_CharacterWrapper`

.. function:: removeConstraint(constraintId)

   Removes a constraint.

   :arg constraintId: The id of the constraint to be removed.
   :type constraintId: int

.. function:: setCcdMode(ccdMode)

   .. note::
      Very experimental, not recommended

   Sets the CCD (Continous Colision Detection) mode in the Physics Environment.

   :arg ccdMode: The new CCD mode.
   :type ccdMode: int

.. function:: setContactBreakingTreshold(breakingTreshold)

   .. note::
      Reasonable default is 0.02 (if units are meters)

   Sets tresholds to do with contact point management.

   :arg breakingTreshold: The new contact breaking treshold.
   :type breakingTreshold: float

.. function:: setDeactivationAngularTreshold(angularTreshold)

   Sets the angular velocity treshold.

   :arg angularTreshold: New deactivation angular treshold.
   :type angularTreshold: float

.. function:: setDeactivationLinearTreshold(linearTreshold)

   Sets the linear velocity treshold.

   :arg linearTreshold: New deactivation linear treshold.
   :type linearTreshold: float

.. function:: setDeactivationTime(time)

   Sets the time after which a resting rigidbody gets deactived.

   :arg time: The deactivation time.
   :type time: float

.. function:: setDebugMode(mode)

   Sets the debug mode.

   :arg mode: The new debug mode, see `Debug Mode Constants`_.

   :type mode: int

.. function:: setGravity(x, y, z)

   Sets the gravity force.

   :arg x: Gravity X force.
   :type x: float

   :arg y: Gravity Y force.
   :type y: float

   :arg z: Gravity Z force.
   :type z: float

.. function:: setLinearAirDamping(damping)

   .. note::

      Not implemented

   Sets the linear air damping for rigidbodies.

.. function:: setNumIterations(numiter)

   Sets the number of iterations for an iterative constraint solver.

   :arg numiter: New number of iterations.
   :type numiter: int

.. function:: setNumTimeSubSteps(numsubstep)

   Sets the number of substeps for each physics proceed. Tradeoff quality for performance.

   :arg numsubstep: New number of substeps.
   :type numsubstep: int

.. function:: setSolverDamping(damping)

   .. note::
      Very experimental, not recommended

   Sets the damper constant of a penalty based solver.

   :arg damping: New damping for the solver.
   :type damping: float

.. function:: setSolverTau(tau)

   .. note::
      Very experimental, not recommended

   Sets the spring constant of a penalty based solver.

   :arg tau: New tau for the solver.
   :type tau: float

.. function:: setSolverType(solverType)

   .. note::
      Very experimental, not recommended

   Sets the solver type.

   :arg solverType: The new type of the solver.
   :type solverType: int

.. function:: setSorConstant(sor)

   .. note::
      Very experimental, not recommended

   Sets the successive overrelaxation constant.

   :arg sor: New sor value.
   :type sor: float

.. function:: setUseEpa(epa)

   .. note::

      Not implemented


Constants
+++++++++

.. attribute:: error

   Symbolic constant string that indicates error.

   :type: str


Debug Mode Constants
^^^^^^^^^^^^^^^^^^^^

Debug mode to be used with :func:`setDebugMode`.


.. data:: DBG_NODEBUG

   No debug.

.. data:: DBG_DRAWWIREFRAME

   Draw wireframe in debug.

.. data:: DBG_DRAWAABB

   Draw Axis Aligned Bounding Box in debug.

.. data:: DBG_DRAWFREATURESTEXT

   Draw features text in debug.

.. data:: DBG_DRAWCONTACTPOINTS

   Draw contact points in debug.

.. data:: DBG_NOHELPTEXT

   Debug without help text.

.. data:: DBG_DRAWTEXT

   Draw text in debug.

.. data:: DBG_PROFILETIMINGS

   Draw profile timings in debug.

.. data:: DBG_ENABLESATCOMPARISION

   Enable sat comparision in debug.

.. data:: DBG_DISABLEBULLETLCP

   Disable Bullet LCP.

.. data:: DBG_ENABLECCD

   Enable Continous Collision Detection in debug.

.. data:: DBG_DRAWCONSTRAINTS

   Draw constraints in debug.

.. data:: DBG_DRAWCONSTRAINTLIMITS

   Draw constraint limits in debug.

.. data:: DBG_FASTWIREFRAME

   Draw a fast wireframe in debug.


Create Constraint Constants
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Constraint type to be used with :func:`createConstraint`.


.. data:: POINTTOPOINT_CONSTRAINT

   .. to do

.. data:: LINEHINGE_CONSTRAINT

   .. to do

.. data:: ANGULAR_CONSTRAINT

   .. to do

.. data:: CONETWIST_CONSTRAINT

   .. to do

.. data:: VEHICLE_CONSTRAINT

   .. to do

.. data:: GENERIC_6DOF_CONSTRAINT

   .. to do

