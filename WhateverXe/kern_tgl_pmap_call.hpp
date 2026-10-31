#pragma once

#include <stdint.h>
#include <string.h>

// Verify an x86-64 CALL rel32 by its resolved destination, not by the
// kernel-build-specific displacement bytes.
static inline bool tglSequoiaPmapCallMatches(uintptr_t callSite, uintptr_t target) {
 if (!callSite || !target) return false;
 const auto *code=reinterpret_cast<const uint8_t *>(callSite);
 if (code[0]!=0xE8) return false;
 int32_t displacement=0;
 memcpy(&displacement,code+1,sizeof(displacement));
 return callSite+5+static_cast<uintptr_t>(static_cast<intptr_t>(displacement))==target;
}
