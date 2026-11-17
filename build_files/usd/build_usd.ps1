# BGE-Remix (P12): builds oneTBB and OpenUSD for the bridge on Windows.
#   build_usd.ps1 -Tbb <oneTBB checkout> -Usd <OpenUSD checkout> -Out <SDK folder>
# oneTBB 2021.12 (Remix 1.6.1 ships the same): tbb12.dll, built as usual
# (its own C runtime, /MD). OpenUSD 25.11: C++ only (no Python, imaging,
# tools, tests or examples), one static library (usd_m.lib) with the static
# C runtime (/MT) like Blender 2.79 and the bridge, its own namespace
# (pxrBgeRemix_v0_25_11) and plugin-path variable (BGE_REMIX_USD_PLUGINPATH).
# PXR_STATIC everywhere: no dllexport in the library, so bge_remix_usd.dll does
# not export OpenUSD's functions (it is compiled with PXR_STATIC too).
# The result:
#   <Out>/include          OpenUSD's and oneTBB's headers
#   <Out>/lib/usd_m.lib    OpenUSD (linked whole into bge_remix_usd.dll)
#   <Out>/lib/tbb12.lib    oneTBB's import library
#   <Out>/bin/tbb12.dll    installed beside blender.exe
#   <Out>/usd              OpenUSD's plugin descriptions, installed as the
#                          usd folder beside blender.exe
param(
	[Parameter(Mandatory = $true)][string]$Tbb,
	[Parameter(Mandatory = $true)][string]$Usd,
	[Parameter(Mandatory = $true)][string]$Out
)
$ErrorActionPreference = "Stop"
$Tbb = (Resolve-Path $Tbb).Path
$Usd = (Resolve-Path $Usd).Path
New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
$work = Join-Path (Split-Path -Parent $Out) "usd_work"
$tbbInstall = "$work/tbb_install"
$usdInstall = "$work/usd_install"

# oneTBB
cmake -S $Tbb -B "$work/tbb_build" -G "Visual Studio 17 2022" -A x64 `
	-DTBB_TEST=OFF -DTBB_EXAMPLES=OFF -DTBB_STRICT=OFF -DTBBMALLOC_BUILD=OFF `
	-DCMAKE_INSTALL_PREFIX="$tbbInstall"
if ($LASTEXITCODE -ne 0) { throw "oneTBB: cmake failed" }
cmake --build "$work/tbb_build" --config Release --target install -- /m /v:minimal
if ($LASTEXITCODE -ne 0) { throw "oneTBB build failed" }

# OpenUSD
# OpenUSD 25.11's own CMake installs usd_m's .pdb on Windows, which a static
# library does not have (CMake refuses: "TARGET_PDB_FILE is allowed only for
# targets with linker created artifacts"): only for a shared usd_m
$public = "$Usd/cmake/macros/Public.cmake"
$text = Get-Content $public -Raw
$pdb = '(?s)if\(WIN32\)(\s*install\(\s*FILES \$<TARGET_PDB_FILE:usd_m>)'
if ($text -notmatch $pdb) { throw "usd_m's pdb install was not found in $public" }
$text = [regex]::Replace($text, $pdb, 'if(WIN32 AND BUILD_SHARED_LIBS)$1')
Set-Content $public $text -NoNewline
cmake -S $Usd -B "$work/usd_build" -G "Visual Studio 17 2022" -A x64 `
	-DCMAKE_INSTALL_PREFIX="$usdInstall" `
	-DCMAKE_PREFIX_PATH="$tbbInstall" -DTBB_ROOT="$tbbInstall" `
	-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded `
	-DCMAKE_CXX_FLAGS="/DWIN32 /D_WINDOWS /GR /EHsc /DPXR_STATIC=1" `
	-DBUILD_SHARED_LIBS=OFF -DPXR_BUILD_MONOLITHIC=ON `
	-DPXR_SET_INTERNAL_NAMESPACE=pxrBgeRemix_v0_25_11 `
	-DPXR_OVERRIDE_PLUGINPATH_NAME=BGE_REMIX_USD_PLUGINPATH `
	-DPXR_ENABLE_PYTHON_SUPPORT=OFF -DPXR_ENABLE_GL_SUPPORT=OFF -DPXR_ENABLE_MATERIALX_SUPPORT=OFF `
	-DPXR_BUILD_IMAGING=OFF -DPXR_BUILD_USD_IMAGING=OFF -DPXR_BUILD_USDVIEW=OFF `
	-DPXR_BUILD_USD_TOOLS=OFF -DPXR_BUILD_USD_VALIDATION=OFF -DPXR_BUILD_EXEC=OFF `
	-DPXR_BUILD_TESTS=OFF -DPXR_BUILD_EXAMPLES=OFF -DPXR_BUILD_TUTORIALS=OFF `
	-DPXR_BUILD_HTML_DOCUMENTATION=OFF
if ($LASTEXITCODE -ne 0) { throw "OpenUSD: cmake failed" }
cmake --build "$work/usd_build" --config Release --target install -- /m /v:minimal
if ($LASTEXITCODE -ne 0) { throw "OpenUSD build failed" }

# the SDK
New-Item -ItemType Directory -Force "$Out/include", "$Out/lib", "$Out/bin" | Out-Null
Copy-Item "$usdInstall/include/*" "$Out/include" -Recurse -Force
Copy-Item "$tbbInstall/include/*" "$Out/include" -Recurse -Force
Copy-Item "$usdInstall/lib/usd_m.lib" "$Out/lib/usd_m.lib" -Force
Copy-Item "$tbbInstall/lib/tbb12.lib" "$Out/lib/tbb12.lib" -Force
Copy-Item "$tbbInstall/bin/tbb12.dll" "$Out/bin/tbb12.dll" -Force
Copy-Item "$usdInstall/lib/usd" "$Out/usd" -Recurse -Force
Copy-Item "$Usd/LICENSE.txt" "$Out/LICENSE_OpenUSD.txt" -Force
Copy-Item "$Usd/NOTICE.txt" "$Out/NOTICE_OpenUSD.txt" -Force
Copy-Item "$Tbb/LICENSE.txt" "$Out/LICENSE_oneTBB.txt" -Force

$need = "lib/usd_m.lib", "lib/tbb12.lib", "bin/tbb12.dll", "usd/plugInfo.json", "include/pxr/pxr.h", "include/tbb/version.h"
foreach ($f in $need) {
	if (-not (Test-Path "$Out/$f")) { throw "missing $f in $Out" }
}
Select-String -Path "$Out/include/pxr/pxr.h" -Pattern "PXR_INTERNAL_NS |PXR_VERSION " | ForEach-Object { $_.Line }
Get-ChildItem "$Out/lib", "$Out/bin" | Select-Object Name, Length | Format-Table -AutoSize
Remove-Item -Recurse -Force $work
