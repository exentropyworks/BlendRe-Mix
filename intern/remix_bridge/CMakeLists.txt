# ***** BEGIN GPL LICENSE BLOCK *****
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# ***** END GPL LICENSE BLOCK *****

# BGE-Remix: bge_remix_bridge.dll, the only code that talks to RTX Remix.
# C++17 inside, a plain C interface outside (bge_remix_bridge.h), so the rest
# of Blender stays C/C++11. Installed next to blender.exe.

# RTX Remix needs Windows 10, and DirectXTex's header Windows 8+ (Blender
# itself targets Vista)
remove_definitions(-D_WIN32_WINNT=0x600)
add_definitions(-D_WIN32_WINNT=0x0A00)

add_library(bge_remix_bridge SHARED
	bridge.cpp
	bridge_device.cpp
	bridge_load.cpp
	bridge_read.cpp
	bridge_scene.cpp
	bridge_startup.cpp
	bridge_texture.cpp
	bridge_triangle.cpp
	bridge_usd_api.cpp

	bge_remix_bridge.h
	bridge_intern.h
)

target_include_directories(bge_remix_bridge PRIVATE
	${CMAKE_CURRENT_SOURCE_DIR}
	${CMAKE_SOURCE_DIR}/extern/remix_sdk
)

target_link_libraries(bge_remix_bridge user32 gdi32 opengl32 extern_directxtex)

if(MSVC)
	# /EHs /EHc-: C++ exceptions may come out of extern "C" functions. Remix's
	# shim throws through remixapi_InitializeLibrary; with the usual /EHsc the
	# compiler assumes extern "C" never throws and drops our catch blocks.
	target_compile_options(bge_remix_bridge PRIVATE /std:c++17 /EHs /EHc- /utf-8)
endif()

install(TARGETS bge_remix_bridge RUNTIME DESTINATION ".")

# BGE-Remix P12: OpenUSD 25.11 in a DLL of its own, bge_remix_usd.dll
# (usd/CMakeLists.txt), which the bridge loads on the first import, export or
# check (bridge_usd_api.cpp). Without USD_ROOT_DIR it is not built, and the
# bridge's USD calls say so.
if(USD_ROOT_DIR)
	add_subdirectory(usd)
	add_dependencies(bge_remix_bridge bge_remix_usd)
endif()
