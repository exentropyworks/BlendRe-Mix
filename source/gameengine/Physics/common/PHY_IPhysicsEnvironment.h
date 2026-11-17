/*
 * ***** BEGIN GPL LICENSE BLOCK *****
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software Foundation,
 * Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
 *
 * The Original Code is Copyright (C) 2001-2002 by NaN Holding BV.
 * All rights reserved.
 *
 * The Original Code is: all of this file.
 *
 * Contributor(s): none yet.
 *
 * ***** END GPL LICENSE BLOCK *****
 */

/** \file PHY_IPhysicsEnvironment.h
 *  \ingroup phys
 */

#ifndef __PHY_IPHYSICSENVIRONMENT_H__
#define __PHY_IPHYSICSENVIRONMENT_H__

#include "PHY_DynamicTypes.h"
#include "MT_Vector2.h"
#include "MT_Vector3.h"
#include "MT_Vector4.h"

#ifdef WITH_CXX_GUARDEDALLOC
#include "MEM_guardedalloc.h"
#endif

#include <vector>  /* BGE-Remix P11 (B1) */

class PHY_IVehicle;
class PHY_ICharacter;
class RAS_MeshObject;
class PHY_IPhysicsController;


class RAS_MeshObject;
struct DerivedMesh;
class KX_GameObject;
class KX_Scene;

struct PHY_ShapeProps;
struct PHY_MaterialProps;
class PHY_IMotionState;
struct bRigidBodyJointConstraint;

/**
 * pass back information from rayTest
 */
/* BGE-Remix P11 (B1): an articulation (PhysX: a tree of bodies solved as
 * one), as the game sees it */
struct PHY_ArticulationInfo
{
	PHY_IPhysicsController *root;
	bool fixed;                                  /* the root fixed to the world */
	std::vector<PHY_IPhysicsController *> links; /* the root first, each after its parent */
	std::vector<int> joints;                     /* each link's joint to its parent (0: the root) */
	std::vector<int> parents;                    /* each link's parent (an index; -1: the root) */
	std::vector<int> ordinary;                   /* its bodies' joints left ordinary (a loop, ...) */
	PHY_ArticulationInfo() : root(NULL), fixed(false) {}
};

/* BGE-Remix P11 (B2): a destructible (NVIDIA Blast, PhysX), as the game
 * sees it: its pieces (game objects' controllers), the groups they are in now */
struct PHY_DestructibleInfo
{
	PHY_IPhysicsController *root;                /* the piece Make Destructible made the parent */
	std::vector<PHY_IPhysicsController *> pieces; /* every piece still in the game */
	std::vector<int> groupOf;                    /* each piece's group (0: the one still held, if any) */
	int groups;                                  /* how many groups the pieces are in */
	int bonds, bondsBroken;
	bool anchored;
	float strength;
	PHY_DestructibleInfo() : root(NULL), groups(0), bonds(0), bondsBroken(0), anchored(false), strength(0.0f) {}
};

/* BGE-Remix P11 (B3): a fluid volume (PhysX: water or lava that things
 * float in, are slowed by and carried along by), as the game sees it */
struct PHY_FluidInfo
{
	int type;                                    /* 0 water, 1 lava */
	float density;                               /* kg/m3 */
	float drag;                                  /* per second, moving and turning */
	MT_Vector3 current;                          /* m/s, along the volume's own axes */
	bool splashes;
	std::vector<PHY_IPhysicsController *> inside; /* the objects in it now */
	PHY_FluidInfo() : type(0), density(1000.0f), drag(2.0f), current(0.0, 0.0, 0.0), splashes(true) {}
};

/* a splash: where a body crossed a fluid volume's surface */
struct PHY_FluidSplash
{
	MT_Vector3 point;                            /* on the surface (world) */
	MT_Vector3 up;                               /* the surface's normal */
	float size;                                  /* the body's size (m) */
	float speed;                                 /* how fast it crossed (m/s) */
	int type;                                    /* the volume's: 0 water, 1 lava */
	PHY_FluidSplash() : point(0.0, 0.0, 0.0), up(0.0, 0.0, 1.0), size(1.0f), speed(0.0f), type(0) {}
};

struct PHY_RayCastResult
{
	PHY_IPhysicsController* m_controller;
	MT_Vector3			m_hitPoint;
	MT_Vector3			m_hitNormal;
	const RAS_MeshObject*	m_meshObject;	// !=NULL for mesh object (only for Bullet controllers) 
	int						m_polygon;		// index of the polygon hit by the ray,
											// only if m_meshObject != NULL
	int                     m_hitUVOK;		// !=0 if UV coordinate in m_hitUV is valid
	MT_Vector2			m_hitUV;		// UV coordinates of hit point
};

/**
 * This class replaces the ignoreController parameter of rayTest function. 
 * It allows more sophisticated filtering on the physics controller before computing the ray intersection to save CPU. 
 * It is only used to its full extend by the Ccd physics environment (Bullet).
 */
class PHY_IRayCastFilterCallback
{
public:
	PHY_IPhysicsController* m_ignoreController;
	bool					m_faceNormal;
	bool					m_faceUV;

	virtual		~PHY_IRayCastFilterCallback()
	{
	}

	virtual	bool needBroadphaseRayCast(PHY_IPhysicsController* controller)
	{
		return true;
	}

	virtual void reportHit(PHY_RayCastResult* result) = 0;

	PHY_IRayCastFilterCallback(PHY_IPhysicsController* ignoreController, bool faceNormal=false, bool faceUV=false) 
		:m_ignoreController(ignoreController),
		m_faceNormal(faceNormal),
		m_faceUV(faceUV)
	{
	}


#ifdef WITH_CXX_GUARDEDALLOC
	MEM_CXX_CLASS_ALLOC_FUNCS("GE:PHY_IRayCastFilterCallback")
#endif
};

/**
 * Physics Environment takes care of stepping the simulation and is a container for physics entities
 * (rigidbodies,constraints, materials etc.)
 * A derived class may be able to 'construct' entities by loading and/or converting
 */
class PHY_IPhysicsEnvironment
{
	public:
		virtual		~PHY_IPhysicsEnvironment() {}
		virtual	void		BeginFrame() = 0;
		virtual void		EndFrame() = 0;
		/// Perform an integration step of duration 'timeStep'.
		virtual	bool		ProceedDeltaTime(double curTime,float timeStep,float interval)=0;
		///draw debug lines (make sure to call this during the render phase, otherwise lines are not drawn properly)
		virtual void		DebugDrawWorld() {}
		virtual	void		SetFixedTimeStep(bool useFixedTimeStep,float fixedTimeStep)=0;
		//returns 0.f if no fixed timestep is used
		virtual	float		GetFixedTimeStep()=0;

		///getDebugMode return the actual debug visualization state
		virtual int			GetDebugMode()const=0;
		///setDebugMode is used to support several ways of debug lines, contact point visualization
		virtual void		SetDebugMode(int debugMode) {}
		///setNumIterations set the number of iterations for iterative solvers
		virtual void		SetNumIterations(int numIter) {}
		///setNumTimeSubSteps set the number of divisions of the timestep. Tradeoff quality versus performance.
		virtual void		SetNumTimeSubSteps(int numTimeSubSteps) {}
		virtual int			GetNumTimeSubSteps() {return 0; }
		///setDeactivationTime sets the minimum time that an objects has to stay within the velocity tresholds until it gets fully deactivated
		virtual void		SetDeactivationTime(float dTime) {}
		///setDeactivationLinearTreshold sets the linear velocity treshold, see setDeactivationTime
		virtual	void		SetDeactivationLinearTreshold(float linTresh) {}
		///setDeactivationAngularTreshold sets the angular velocity treshold, see setDeactivationTime
		virtual	void		SetDeactivationAngularTreshold(float angTresh) {}
		///setContactBreakingTreshold sets tresholds to do with contact point management
		virtual void		SetContactBreakingTreshold(float contactBreakingTreshold) {}
		///continuous collision detection mode, very experimental for Bullet
		virtual void		SetCcdMode(int ccdMode) {}
		///successive overrelaxation constant, in case PSOR is used, values in between 1 and 2 guarantee converging behavior
		virtual void		SetSolverSorConstant(float sor) {}
		///setSolverType, internal setting, chooses solvertype, PSOR, Dantzig, impulse based, penalty based
		virtual void		SetSolverType(int solverType) {}
		///setTau sets the spring constant of a penalty based solver
		virtual void		SetSolverTau(float tau) {}
		///setDamping sets the damper constant of a penalty based solver
		virtual void		SetSolverDamping(float damping) {}
		///linear air damping for rigidbodies
		virtual void		SetLinearAirDamping(float damping) {}
		/// penetrationdepth setting
		virtual void		SetUseEpa(bool epa) {}

		virtual	void		SetGravity(float x,float y,float z)=0;
		virtual	void		GetGravity(MT_Vector3& grav) = 0;

		virtual int			CreateConstraint(class PHY_IPhysicsController* ctrl,class PHY_IPhysicsController* ctrl2,PHY_ConstraintType type,
			float pivotX,float pivotY,float pivotZ,
			float axis0X,float axis0Y,float axis0Z,
			float axis1X=0,float axis1Y=0,float axis1Z=0,
			float axis2X=0,float axis2Y=0,float axis2Z=0,int flag=0
		)=0;
		virtual void RemoveConstraintById(int constraintid) = 0;
		virtual float		GetAppliedImpulse(int	constraintid) { return 0.0f; }


		//complex constraint for vehicles
		virtual PHY_IVehicle*	GetVehicleConstraint(int constraintId) =0;

		// Character physics wrapper
		virtual PHY_ICharacter*	GetCharacterController(class KX_GameObject* ob) =0;

		virtual PHY_IPhysicsController* RayTest(PHY_IRayCastFilterCallback &filterCallback, float fromX,float fromY,float fromZ, float toX,float toY,float toZ)=0;

		//culling based on physical broad phase
		// the plane number must be set as follow: near, far, left, right, top, botton
		// the near plane must be the first one and must always be present, it is used to get the direction of the view
		virtual bool CullingTest(PHY_CullingCallback callback, void *userData, MT_Vector4* planeNormals, int planeNumber, int occlusionRes, const int *viewport, float modelview[16], float projection[16]) = 0;

		//Methods for gamelogic collision/physics callbacks
		//todo:
		virtual void AddSensor(PHY_IPhysicsController* ctrl)=0;
		virtual void RemoveSensor(PHY_IPhysicsController* ctrl)=0;
		virtual void AddTouchCallback(int response_class, PHY_ResponseCallback callback, void *user)=0;
		virtual bool RequestCollisionCallback(PHY_IPhysicsController* ctrl)=0;
		virtual bool RemoveCollisionCallback(PHY_IPhysicsController* ctrl)=0;
		//These two methods are *solely* used to create controllers for sensor! Don't use for anything else
		virtual PHY_IPhysicsController*	CreateSphereController(float radius,const MT_Vector3& position) =0;
		virtual PHY_IPhysicsController* CreateConeController(float coneradius,float coneheight)=0;
		
		virtual void	SetConstraintParam(int constraintId,int param,float value,float value1) = 0;
		virtual float	GetConstraintParam(int constraintId,int param) = 0;
		
		virtual void	ExportFile(const char* filename) {};

		virtual void MergeEnvironment(PHY_IPhysicsEnvironment *other_env) = 0;

		virtual void ConvertObject(KX_GameObject* gameobj,
							RAS_MeshObject* meshobj,
							DerivedMesh* dm,
							KX_Scene* kxscene,
							PHY_ShapeProps* shapeprops,
							PHY_MaterialProps*	smmaterial,
							PHY_IMotionState *motionstate,
							int activeLayerBitInfo,
							bool isCompoundChild,
							bool hasCompoundChildren) = 0;

		/* BGE-Remix P11 (B1): articulations (PhysX only; the others have none).
		 * The articulation the body is a link of (false: none). */
		virtual bool GetArticulation(PHY_IPhysicsController *ctrl, PHY_ArticulationInfo *info) { return false; }
		/* An articulation joint's position and speed on one axis (0-2 sliding
		 * X Y Z, 3-5 turning X Y Z; -1 the joint's first moving axis). */
		virtual bool GetArticulationJoint(int constraintId, int axis, float *pos, float *vel) { return false; }
		/* Drive an articulation joint's axis to a position (target) and/or a
		 * speed (velocity); maxForce <= 0: no limit. */
		virtual bool SetArticulationDrive(int constraintId, int axis, const float *target, const float *velocity,
		                                  float stiffness, float damping, float maxForce) { return false; }
		/* Why a joint of an articulation's body is not in the articulation
		 * (NULL: it is, or it has no articulation). */
		virtual const char *GetArticulationNote(int constraintId) { return NULL; }
		/* What an articulation joint does now, for the Remix View: -1 not an
		 * articulation joint, 0 at rest, 1 moving, 2 at a limit, 3 driven (a
		 * motor, a spring, a target or speed set); its first moving axis and
		 * the position there. */
		virtual int GetArticulationJointActivity(int constraintId, int *r_axis, float *r_pos) { return -1; }

		/* BGE-Remix P11 (B2): destruction (PhysX with NVIDIA Blast; the others
		 * keep a destructible whole). Whether this engine breaks them. */
		virtual bool HandlesDestruction() { return false; }
		/* The destructible a piece belongs to (false: none, or not broken by this engine). */
		virtual bool GetDestructible(PHY_IPhysicsController *piece, PHY_DestructibleInfo *info) { return false; }
		/* Damage around a point (world): 1 breaks a bond at the point, less
		 * at the radius; false: not a destructible's piece. */
		virtual bool DamageDestructible(PHY_IPhysicsController *piece, const MT_Vector3 &point, float radius,
		                                float amount) { return false; }
		virtual void SetDestructibleStrength(PHY_IPhysicsController *piece, float strength) {}
		/* Every destructible within the radius: how many were hit. */
		virtual int Explode(const MT_Vector3 &point, float radius, float amount) { return 0; }
		/* The scene's budget: the most broken-off pieces (0: no limit), and
		 * how long they stay (seconds; 0: until the budget needs room). */
		virtual void SetDestructionBudget(int maxPieces, float lifetime) {}
		/* The pieces the budget removes (the game ends their objects). */
		virtual void TakeDestructionRemovals(std::vector<PHY_IPhysicsController *> &r_pieces) {}
		/* What a destructible does now, for the Remix View: -1 none, 0 whole
		 * or at rest, 1 breaking, 2 the budget has taken pieces of it, 3
		 * damaged by a script just now. */
		virtual int GetDestructionActivity(PHY_IPhysicsController *piece) { return -1; }

		/* BGE-Remix P11 (B3): fluid volumes (PhysX; the others leave them
		 * ghosts things fall through). The volume of a volume's object
		 * (false: not one, or not this engine's). */
		virtual bool GetFluid(PHY_IPhysicsController *volume, PHY_FluidInfo *info) { return false; }
		virtual void SetFluidCurrent(PHY_IPhysicsController *volume, const MT_Vector3 &current) {}
		/* How much of an object is under the volume's surface, 0 to 1. */
		virtual float GetSubmerged(PHY_IPhysicsController *volume, PHY_IPhysicsController *ctrl) { return 0.0f; }
		/* The splashes since the last call (the game shows them). */
		virtual void TakeFluidSplashes(std::vector<PHY_FluidSplash> &r_splashes) {}
		/* For the Remix View: a volume's activity (-1 not a volume, 0 nothing
		 * in it, 1 something in it, 3 a splash just now), and an object's
		 * state in fluids (-1 in none, 1 it floats, 2 it sinks). */
		virtual int GetFluidActivity(PHY_IPhysicsController *volume) { return -1; }
		virtual int GetFluidState(PHY_IPhysicsController *ctrl) { return -1; }

		/* Set the rigid body joints constraints values for converted objects and replicated group instances. */
		virtual void SetupObjectConstraints(KX_GameObject *obj_src, KX_GameObject *obj_dest,
		                                    bRigidBodyJointConstraint *dat) {}

#ifdef WITH_CXX_GUARDEDALLOC
	MEM_CXX_CLASS_ALLOC_FUNCS("GE:PHY_IPhysicsEnvironment")
#endif
};

#endif  /* __PHY_IPHYSICSENVIRONMENT_H__ */
