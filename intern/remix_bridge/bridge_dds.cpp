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
 * ***** END GPL LICENSE BLOCK *****
 */

/** \file bridge_dds.cpp
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12 round 2: a DDS texture of a capture decoded to a PNG that
 * Blender shows (brb_dds_to_png), with DirectXTex: any format Remix or a
 * game writes (block-compressed or not), its first mip level, rows as the
 * file has them (from the top).
 */

#include <cstdio>
#include <string>

#include "bridge_intern.h"

#include <DirectXTex.h>

namespace {

std::string hr_text(HRESULT hr)
{
	char buf[32];
	snprintf(buf, sizeof(buf), "0x%08lX", (unsigned long)hr);
	return buf;
}

bool decode(const wchar_t *dds, const wchar_t *png, std::string &r_error)
{
	DirectX::TexMetadata meta;
	DirectX::ScratchImage src;
	HRESULT hr = DirectX::LoadFromDDSFile(dds, DirectX::DDS_FLAGS_NONE, &meta, src);
	if (FAILED(hr)) {
		r_error = "not a DDS file DirectXTex can read (" + hr_text(hr) + ")";
		return false;
	}
	const DirectX::Image *img = src.GetImage(0, 0, 0);
	if (!img) {
		r_error = "the DDS file holds no picture";
		return false;
	}
	DirectX::ScratchImage plain;
	if (DirectX::IsCompressed(img->format)) {
		hr = DirectX::Decompress(*img, DXGI_FORMAT_R8G8B8A8_UNORM, plain);
		if (FAILED(hr)) {
			r_error = "its compressed format could not be decoded (" + hr_text(hr) + ")";
			return false;
		}
		img = plain.GetImage(0, 0, 0);
	}
	DirectX::ScratchImage rgba;
	if (img->format != DXGI_FORMAT_R8G8B8A8_UNORM) {
		hr = DirectX::Convert(*img, DXGI_FORMAT_R8G8B8A8_UNORM, DirectX::TEX_FILTER_DEFAULT,
		                      DirectX::TEX_THRESHOLD_DEFAULT, rgba);
		if (FAILED(hr)) {
			r_error = "its format could not be turned into RGBA (" + hr_text(hr) + ")";
			return false;
		}
		img = rgba.GetImage(0, 0, 0);
	}
	/* WIC needs COM on this thread; it stays on (P12 round 2: DirectXTex
	 * keeps its WIC factory once made, and a CoUninitialize after the first
	 * PNG released it under it, so the second one crashed). Already on in
	 * another mode (Blender's window thread) is as good. */
	CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
	hr = DirectX::SaveToWICFile(*img, DirectX::WIC_FLAGS_NONE, DirectX::GetWICCodec(DirectX::WIC_CODEC_PNG),
	                            png);
	if (FAILED(hr)) {
		r_error = "the PNG could not be written (" + hr_text(hr) + ")";
		return false;
	}
	return true;
}

/* a crash inside the decoder (a damaged file) is a failure, not Blender's
 * end (no C++ objects here, so __try may hold the call) */
int decode_guarded(const wchar_t *dds, const wchar_t *png, std::string *r_error, unsigned long *r_code)
{
	__try {
		return decode(dds, png, *r_error) ? 1 : 0;
	}
	__except (EXCEPTION_EXECUTE_HANDLER) {
		*r_code = GetExceptionCode();
		return -1;
	}
}

}  // namespace

using namespace brb;

BRB_API int brb_dds_to_png(const wchar_t *dds, const wchar_t *png, char *r_error, int max_bytes)
{
	std::string err;
	bool ok = false;
	if (!dds || !png) {
		err = "no file given";
	}
	else {
		unsigned long code = 0;
		int r = -1;
		try {
			r = decode_guarded(dds, png, &err, &code);
		}
		catch (...) {
			err = "decoding failed";
		}
		ok = r == 1;
		if (r < 0 && code) {
			char buf[64];
			snprintf(buf, sizeof(buf), "decoding crashed (exception 0x%08lX)", code);
			err = buf;
		}
	}
	if (!ok) {
		log("DDS %s: %s", utf8(dds ? dds : L"").c_str(), err.c_str());
	}
	if (r_error && max_bytes > 0) {
		snprintf(r_error, size_t(max_bytes), "%s", err.c_str());
	}
	return ok ? 1 : 0;
}
