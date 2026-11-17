# BGE-Remix P12: the bridge's OpenUSD, checked without Remix or Blender.
# Windows (the GitHub build, after the bridge is built):
#   cmake -S tests/bge_remix/p12/native -B p12native
#   cmake --build p12native --config Release
#   p12native/Release/p12_usd_check.exe <bge_remix_bridge.dll> <folder>
# Elsewhere (the USD code itself, linked in):
#   cmake -S tests/bge_remix/p12/native -B p12native -DUSD_ROOT_DIR=<OpenUSD install> -DTBB_ROOT_DIR=<oneTBB install>
#   p12native/p12_usd_check <folder> [<OpenUSD install>/lib/usd]
cmake_minimum_required(VERSION 3.24)  # LINK_LIBRARY:WHOLE_ARCHIVE
project(p12_usd_check CXX)
set(CMAKE_CXX_STANDARD 17)

get_filename_component(BLENDER "${CMAKE_CURRENT_SOURCE_DIR}/../../../.." ABSOLUTE)
set(USD_SRC "${BLENDER}/intern/remix_bridge/usd")

if(WIN32)
	add_executable(p12_usd_check usd_check.cpp)
	set_property(TARGET p12_usd_check PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
else()
	set(USD_ROOT_DIR "" CACHE PATH "OpenUSD install (static monolithic usd_m)")
	set(TBB_ROOT_DIR "" CACHE PATH "oneTBB install")
	find_library(USD_M NAMES usd_m PATHS "${USD_ROOT_DIR}/lib" NO_DEFAULT_PATH REQUIRED)
	find_library(TBB_LIB NAMES tbb PATHS "${TBB_ROOT_DIR}/lib" NO_DEFAULT_PATH REQUIRED)
	add_executable(p12_usd_check usd_check.cpp "${USD_SRC}/usd_core.cpp")
	target_include_directories(p12_usd_check PRIVATE "${USD_SRC}" "${USD_ROOT_DIR}/include" "${TBB_ROOT_DIR}/include")
	target_compile_definitions(p12_usd_check PRIVATE PXR_STATIC=1)
	target_link_libraries(p12_usd_check "$<LINK_LIBRARY:WHOLE_ARCHIVE,${USD_M}>" "${TBB_LIB}" ${CMAKE_DL_LIBS} pthread)
	set_target_properties(p12_usd_check PROPERTIES BUILD_RPATH "${TBB_ROOT_DIR}/lib")
endif()
