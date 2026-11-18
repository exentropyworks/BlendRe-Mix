# ***** BEGIN GPL LICENSE BLOCK *****
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# ***** END GPL LICENSE BLOCK *****

# BGE-Remix P12: bge_remix_usd.dll, the bridge's OpenUSD (25.11, from
# USD_ROOT_DIR: build_files/usd/build_usd.ps1). OpenUSD is linked in whole
# (a static library with the static C runtime, like Blender's); the DLL has a
# plain C interface (bge_remix_usd.h) and only the bridge loads it, on first
# use. Installed beside blender.exe with tbb12.dll (oneTBB, its threading
# library) and the usd folder (OpenUSD's plugin descriptions).
#
# Compiled as OpenUSD itself was: Blender's /J (char unsigned) would change
# what OpenUSD's inline code does (this folder's flags only).
string(REPLACE "/J" "" CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS}")

if(NOT EXISTS "${USD_ROOT_DIR}/lib/usd_m.lib" OR NOT EXISTS "${USD_ROOT_DIR}/usd/plugInfo.json")
	message(FATAL_ERROR "USD_ROOT_DIR: no OpenUSD in \"${USD_ROOT_DIR}\" (build_files/usd/build_usd.ps1)")
endif()
message(STATUS "OpenUSD for the RTX Remix bridge: ${USD_ROOT_DIR}")

add_library(bge_remix_usd SHARED
	usd_capture.cpp
	usd_core.cpp
	usd_dll.cpp
	usd_dump.cpp

	bge_remix_usd.h
	usd_core.h
)
target_include_directories(bge_remix_usd PRIVATE "${USD_ROOT_DIR}/include")
# a static OpenUSD: no dllimport, and none of its functions exported from
# the DLL (it is built with PXR_STATIC too)
target_compile_definitions(bge_remix_usd PRIVATE PXR_STATIC=1 NOMINMAX WIN32_LEAN_AND_MEAN BGE_REMIX_USD_EXPORTS)
target_link_libraries(bge_remix_usd "${USD_ROOT_DIR}/lib/usd_m.lib" "${USD_ROOT_DIR}/lib/tbb12.lib"
                      Ws2_32 Dbghelp Shlwapi)
if(MSVC)
	target_compile_options(bge_remix_usd PRIVATE /std:c++17 /EHsc /Zc:__cplusplus /Zc:inline- /bigobj /utf-8)
	# all of usd_m: its files register types and plugins from static
	# objects' constructors, which a normal link would drop
	set_property(TARGET bge_remix_usd APPEND_STRING PROPERTY LINK_FLAGS
		" /WHOLEARCHIVE:\"${USD_ROOT_DIR}/lib/usd_m.lib\" /IGNORE:4099")
endif()

install(TARGETS bge_remix_usd RUNTIME DESTINATION ".")
install(FILES "${USD_ROOT_DIR}/bin/tbb12.dll" DESTINATION ".")
install(DIRECTORY "${USD_ROOT_DIR}/usd" DESTINATION ".")
install(FILES "${USD_ROOT_DIR}/LICENSE_OpenUSD.txt" "${USD_ROOT_DIR}/NOTICE_OpenUSD.txt"
              "${USD_ROOT_DIR}/LICENSE_oneTBB.txt" DESTINATION ".")
