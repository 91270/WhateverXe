#include "kern_tgl_pmap_call.hpp"

#include <assert.h>
#include <stdint.h>
#include <string.h>

int main() {
 alignas(16) uint8_t code[8] {};
 const uintptr_t site=reinterpret_cast<uintptr_t>(code);
 const int32_t offsets[] {0x2CB71,0x2CBA1,0,-5,-0x2CBA1};
 for (const auto offset:offsets) {
  code[0]=0xE8;
  memcpy(code+1,&offset,sizeof(offset));
  const auto target=site+5+static_cast<uintptr_t>(static_cast<intptr_t>(offset));
  assert(tglSequoiaPmapCallMatches(site,target));
  assert(!tglSequoiaPmapCallMatches(site,target+1));
  assert(!tglSequoiaPmapCallMatches(site,0));
  code[0]=0xE9;
  assert(!tglSequoiaPmapCallMatches(site,target));
 }
 assert(!tglSequoiaPmapCallMatches(0,site));
 return 0;
}
