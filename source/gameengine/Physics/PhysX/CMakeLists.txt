# ***** BEGIN GPL LICENSE BLOCK *****
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# ***** END GPL LICENSE BLOCK *****

# BGE-Remix (P6): NVIDIA PhysX 5 as the game engine's second physics engine,
# chosen per scene in World > Physics. Uses Bullet's mesh reader
# (CcdShapeConstructionInfo) and Bullet's view culling tree, so it needs
# WITH_BULLET.

remove_strict_flags()

set(INC
	.
	../common
	../Bullet
	../Dummy
	../../BlenderRoutines
	../../Converter
	../../Expressions
	../../GameLogic
	../../Ketsji
	../../Ketsji/KXNetwork
	../../Network
	../../Network/LoopBackNetwork
	../../Rasterizer
	../../Rasterizer/RAS_OpenGLRasterizer
	../../SceneGraph
	../../../blender
	../../../blender/blenkernel
	../../../blender/blenlib
	../../../blender/blenloader
	../../../blender/gpu
	../../../blender/imbuf
	../../../blender/makesdna
	../../../blender/makesrna
	../../../../intern/container
	../../../../intern/guardedalloc
	../../../../intern/glew-mx
	../../../../intern/string
)

set(INC_SYS
	../../../../intern/moto/include
	../../../../extern/recastnavigation/Detour/Include
	${BULLET_INCLUDE_DIRS}
	${PHYSX_INCLUDE_DIRS}
	${GLEW_INCLUDE_PATH}
	${PYTHON_INCLUDE_DIRS}
)

set(SRC
	PxArticulation.cpp
	PxCharacter.cpp
	PxDeformable.cpp
	PxDestruction.cpp
	PxPhysicsController.cpp
	PxPhysicsConvert.cpp
	PxPhysicsEnvironment.cpp
	PxShapes.cpp
	PxSystem.cpp
	PxVehicle.cpp

	PxArticulation.h
	PxCharacter.h
	PxDeformable.h
	PxDestruction.h
	PxMotionState.h
	PxPhysicsController.h
	PxPhysicsEnvironment.h
	PxShapes.h
	PxSystem.h
	PxVehicle.h
)

# BGE-Remix P11 (B2): NVIDIA Blast (BSD 3-clause), from the PhysX repo's
# blast folder (BLAST_SOURCE_DIR): its core and stress solver, built in here.
# Without it destructibles stay whole.
if(BLAST_SOURCE_DIR AND EXISTS "${BLAST_SOURCE_DIR}/include/lowlevel/NvBlast.h")
	set(_bl "${BLAST_SOURCE_DIR}")
	list(APPEND SRC
		${_bl}/source/sdk/lowlevel/NvBlastActor.cpp
		${_bl}/source/sdk/lowlevel/NvBlastActorSerializationBlock.cpp
		${_bl}/source/sdk/lowlevel/NvBlastAsset.cpp
		${_bl}/source/sdk/lowlevel/NvBlastAssetHelper.cpp
		${_bl}/source/sdk/lowlevel/NvBlastFamily.cpp
		${_bl}/source/sdk/lowlevel/NvBlastFamilyGraph.cpp
		${_bl}/source/sdk/globals/NvBlastGlobals.cpp
		${_bl}/source/sdk/globals/NvBlastInternalProfiler.cpp
		${_bl}/source/sdk/common/NvBlastAssert.cpp
		${_bl}/source/sdk/common/NvBlastAtomic.cpp
		${_bl}/source/sdk/common/NvBlastTime.cpp
		${_bl}/source/sdk/common/NvBlastTimers.cpp
		${_bl}/source/sdk/extensions/stress/NvBlastExtStressSolver.cpp
		${_bl}/source/shared/stress_solver/stress.cpp
	)
	list(APPEND INC_SYS
		${_bl}/include/lowlevel
		${_bl}/include/globals
		${_bl}/include/extensions/stress
		${_bl}/include/shared/NvFoundation
		${_bl}/source/sdk/common
		${_bl}/source/sdk/globals
		${_bl}/source/sdk/lowlevel
		${_bl}/source/shared/NsFoundation/include
		${_bl}/source/shared/stress_solver
		${_bl}/source/shared/utils
	)
	if(WIN32)
		list(APPEND INC_SYS ${_bl}/source/shared/NsFoundation/include/platform/windows
		                    ${CMAKE_CURRENT_SOURCE_DIR}/blast_shim)  # (typeinfo.h, gone from VS 2022)
	else()
		list(APPEND INC_SYS ${_bl}/source/shared/NsFoundation/include/platform/unix)
		set_source_files_properties(${_bl}/source/sdk/extensions/stress/NvBlastExtStressSolver.cpp
		                            ${_bl}/source/shared/stress_solver/stress.cpp
		                            PROPERTIES COMPILE_FLAGS "-include limits -mavx -mfma")
	endif()
	add_definitions(-DWITH_BLAST)
	message(STATUS "PhysX: NVIDIA Blast from ${BLAST_SOURCE_DIR}")
else()
	message(STATUS "PhysX: no NVIDIA Blast (BLAST_SOURCE_DIR): destructibles stay whole")
endif()

add_definitions(-DWITH_BULLET -DWITH_PHYSX ${GL_DEFINITIONS})
if(WIN32)
	add_definitions(-DNOMINMAX)
endif()

blender_add_lib(ge_phys_physx "${SRC}" "${INC}" "${INC_SYS}")
