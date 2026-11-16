# BGE-Remix P6: native checks of the PhysX backend (no Blender, CPU scenes).
#   cmake -S tests/bge_remix/p6/native -B p6native -DPHYSX_ROOT_DIR=<SDK>
#   cmake --build p6native --config Release
#   p6native/Release/p6_physx_checks.exe [test name]
cmake_minimum_required(VERSION 3.15)  # MSVC_RUNTIME_LIBRARY (/MT like the PhysX build)
project(p6_physx_checks CXX)
set(CMAKE_CXX_STANDARD 14)  # as Blender 2.79 (std::byte would clash)

set(PHYSX_ROOT_DIR "" CACHE PATH "PhysX 5 SDK (include/, bin/<platform>/release/)")
get_filename_component(BLENDER "${CMAKE_CURRENT_SOURCE_DIR}/../../../.." ABSOLUTE)
set(GE "${BLENDER}/source/gameengine")

file(GLOB _libdirs "${PHYSX_ROOT_DIR}/bin/*/release")
list(GET _libdirs 0 PHYSX_LIBRARY_DIR)
set(PHYSX_LIBS)
foreach(_lib PhysXCharacterKinematic PhysXExtensions PhysX PhysXCooking PhysXCommon PhysXPvdSDK PhysXFoundation)
	find_library(PHYSX_${_lib} NAMES ${_lib}_static_64 PATHS "${PHYSX_LIBRARY_DIR}" NO_DEFAULT_PATH REQUIRED)
	list(APPEND PHYSX_LIBS ${PHYSX_${_lib}})
endforeach()

file(GLOB MOTO_SRC "${BLENDER}/intern/moto/intern/*.cpp")
set(SRC
	harness.cpp
	stubs.cpp
	${GE}/Physics/PhysX/PxArticulation.cpp  # BGE-Remix P11 (B1)
	${GE}/Physics/PhysX/PxCharacter.cpp
	${GE}/Physics/PhysX/PxDeformable.cpp
	${GE}/Physics/PhysX/PxDestruction.cpp  # BGE-Remix P11 (B2)
	${GE}/Physics/PhysX/PxPhysicsController.cpp
	${GE}/Physics/PhysX/PxPhysicsEnvironment.cpp
	${GE}/Physics/PhysX/PxShapes.cpp
	${GE}/Physics/PhysX/PxSystem.cpp
	${GE}/Physics/PhysX/PxVehicle.cpp
	${BLENDER}/extern/bullet2/src/LinearMath/btAlignedAllocator.cpp
	${MOTO_SRC}
)
add_executable(p6_physx_checks ${SRC})
target_include_directories(p6_physx_checks PRIVATE
	"${PHYSX_ROOT_DIR}/include"
	${GE}/Physics/PhysX ${GE}/Physics/common ${GE}/Physics/Bullet ${GE}/Physics/Dummy
	${GE}/Ketsji ${GE}/Ketsji/KXNetwork ${GE}/Converter ${GE}/Expressions ${GE}/GameLogic ${GE}/SceneGraph
	${GE}/Rasterizer ${GE}/BlenderRoutines ${GE}/Network
	${BLENDER}/source/blender ${BLENDER}/source/blender/blenkernel ${BLENDER}/source/blender/blenlib
	${BLENDER}/source/blender/makesdna ${BLENDER}/source/blender/makesrna ${BLENDER}/source/blender/gpu
	${BLENDER}/source/blender/imbuf ${BLENDER}/source/blender/blenloader ${BLENDER}/source/blender/python
	${BLENDER}/intern/container ${BLENDER}/intern/guardedalloc ${BLENDER}/intern/string ${BLENDER}/intern/atomic
	${BLENDER}/intern/moto/include ${BLENDER}/extern/bullet2/src
)
target_compile_definitions(p6_physx_checks PRIVATE WITH_BULLET WITH_PHYSX NDEBUG PX_PHYSX_STATIC_LIB)
# BGE-Remix P11 (B2): NVIDIA Blast (the PhysX repo's blast folder), as the PhysX backend builds it
set(BLAST_SOURCE_DIR "" CACHE PATH "NVIDIA Blast source (the PhysX repo's blast folder)")
if(BLAST_SOURCE_DIR AND EXISTS "${BLAST_SOURCE_DIR}/include/lowlevel/NvBlast.h")
	set(_bl "${BLAST_SOURCE_DIR}")
	set(BLAST_SRC
		${_bl}/source/sdk/lowlevel/NvBlastActor.cpp ${_bl}/source/sdk/lowlevel/NvBlastActorSerializationBlock.cpp
		${_bl}/source/sdk/lowlevel/NvBlastAsset.cpp ${_bl}/source/sdk/lowlevel/NvBlastAssetHelper.cpp
		${_bl}/source/sdk/lowlevel/NvBlastFamily.cpp ${_bl}/source/sdk/lowlevel/NvBlastFamilyGraph.cpp
		${_bl}/source/sdk/globals/NvBlastGlobals.cpp ${_bl}/source/sdk/globals/NvBlastInternalProfiler.cpp
		${_bl}/source/sdk/common/NvBlastAssert.cpp ${_bl}/source/sdk/common/NvBlastAtomic.cpp
		${_bl}/source/sdk/common/NvBlastTime.cpp ${_bl}/source/sdk/common/NvBlastTimers.cpp
		${_bl}/source/sdk/extensions/stress/NvBlastExtStressSolver.cpp ${_bl}/source/shared/stress_solver/stress.cpp)
	target_sources(p6_physx_checks PRIVATE ${BLAST_SRC})
	target_include_directories(p6_physx_checks PRIVATE
		${_bl}/include/lowlevel ${_bl}/include/globals ${_bl}/include/extensions/stress ${_bl}/include/shared/NvFoundation
		${_bl}/source/sdk/common ${_bl}/source/sdk/globals ${_bl}/source/sdk/lowlevel ${_bl}/source/shared/NsFoundation/include
		${_bl}/source/shared/stress_solver ${_bl}/source/shared/utils)
	if(WIN32)
		target_include_directories(p6_physx_checks PRIVATE ${_bl}/source/shared/NsFoundation/include/platform/windows)
	else()
		target_include_directories(p6_physx_checks PRIVATE ${_bl}/source/shared/NsFoundation/include/platform/unix)
		set_source_files_properties(${_bl}/source/sdk/extensions/stress/NvBlastExtStressSolver.cpp
		                            ${_bl}/source/shared/stress_solver/stress.cpp PROPERTIES COMPILE_FLAGS "-include limits -mavx -mfma")
	endif()
	target_compile_definitions(p6_physx_checks PRIVATE WITH_BLAST)
endif()
target_link_libraries(p6_physx_checks ${PHYSX_LIBS})
if(MSVC)
	target_compile_definitions(p6_physx_checks PRIVATE NOMINMAX _CRT_SECURE_NO_WARNINGS)
	set_property(TARGET p6_physx_checks PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
	target_compile_options(p6_physx_checks PRIVATE /EHsc /bigobj)
else()
	target_link_libraries(p6_physx_checks pthread dl)
endif()
