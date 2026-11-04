#include "kern_tgl_ppgtt.hpp"
#include "kern_tgl_hang_refs.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <memory>
#include <vector>

namespace {
constexpr uint64_t OuterBase=0x402d9000ULL;
constexpr uint64_t HangPC=0x402db0c0ULL;
constexpr uint64_t VideoBatch=0x4032e000ULL;
constexpr uint64_t DynamicBase=0x40004000ULL;
constexpr uint64_t Shader0=0x402ec000ULL,Shader1=0x402ed000ULL;
void put(std::vector<uint8_t> &b,unsigned offset,uint32_t value) {
 assert(offset+4<=b.size());std::memcpy(b.data()+offset,&value,4);
}
std::vector<uint8_t> witness() {
 std::vector<uint8_t> b(16384);
 put(b,0x2028,0x6101000e);
 put(b,0x2038,0x40005001);
 put(b,0x2040,0x40004001);
 put(b,0x2050,0x402eb001);
 put(b,0x2068,0x70000007);
 put(b,0x208c,0x70020002);
 put(b,0x2094,0x40);   // two interface descriptors = 64 bytes
 put(b,0x2098,0xc0);   // dynamic base +0xC0
 put(b,0x209c,0x18c00001);
 put(b,0x20a0,static_cast<uint32_t>(VideoBatch));
 put(b,0x20a4,0);
 put(b,0x20a8,0x7a000004);
 put(b,0x20ac,0x001010a2);
 put(b,0x20c0,0x7a000004);
 put(b,0x20c4,0x0000089c);
 return b;
}
void check(const std::vector<uint8_t> &b) {
 assert(b.size()==16384);
 auto c=std::make_unique<TGLHangRefs::Capture>();
 auto read=[](TGLHangRefs::Page &p) {
  p.q[2]=4096;p.q[3]=1;p.q[4]=0;
  if(p.q[0]==VideoBatch) {std::memset(p.bytes,0x5a,4096);return;}
  if(p.q[0]==DynamicBase) {
   const uint32_t shaderOffsets[] {0x1000,0x2000};
   std::memcpy(p.bytes+0xc0,shaderOffsets,4);
   std::memcpy(p.bytes+0xe0,shaderOffsets+1,4);return;
  }
  if(p.q[0]==Shader0 || p.q[0]==Shader1) {
   std::memset(p.bytes,0x5a,4096);return;
  }
  p.q[3]=0;p.q[4]=1;
 };
 TGLHangRefs::collect(*c,b.data(),b.size(),OuterBase,HangPC,read);
 assert(c->q[0]==131);
 assert(c->q[8]==0); // structural anchor parsed
 assert(c->q[5]==0x402db028ULL);
 assert(c->q[9]==0x40005000ULL);
 assert(c->q[10]==0x40004000ULL);
 assert(c->q[11]==0x402eb000ULL);
 assert(c->q[27]==1); // one second-level batch
 assert(c->q[29]==0x400040c0ULL);
 assert(c->q[30]==2);  // two 32-byte IDDs
 assert(c->q[31]==Shader0);
 assert(c->q[6]==4); // external batch + IDD + two ISA pages
 assert(c->pages[0].q[0]==VideoBatch);
 assert(c->pages[0].q[1]==TGLHangRefs::Batch);
 assert(c->pages[0].q[2]==4096 && c->pages[0].q[3]==1);
 assert(c->pages[0].bytes[0]==0x5a);
 assert(c->pages[1].q[0]==DynamicBase);
 assert(c->pages[1].q[1]==TGLHangRefs::Table);
 assert(c->pages[2].q[0]==Shader0 && c->pages[2].q[1]==TGLHangRefs::Shader);
 assert(c->pages[3].q[0]==Shader1 && c->pages[3].q[1]==TGLHangRefs::Shader);
}
}
int main(int argc,char **argv) {
 auto b=witness();check(b);
 auto bad=b;put(bad,0x2028,0);
 auto c=std::make_unique<TGLHangRefs::Capture>();
 auto read=[](TGLHangRefs::Page &){assert(false && "no mapping on invalid SBA");};
 TGLHangRefs::collect(*c,bad.data(),bad.size(),OuterBase,HangPC,read);
 assert(c->q[8]==1 && c->q[6]==0);
 bad=b;put(bad,0x209c,0);put(bad,0x208c,0);
 c=std::make_unique<TGLHangRefs::Capture>();
 TGLHangRefs::collect(*c,bad.data(),bad.size(),OuterBase,HangPC,read);
 assert(c->q[8]==1 && c->q[6]==0);
 if(argc>1) {
  std::ifstream fp(argv[1],std::ios::binary);assert(fp.good());
  std::vector<uint8_t> captured((std::istreambuf_iterator<char>(fp)),
                                std::istreambuf_iterator<char>());
  check(captured);
 }
 std::puts("TGL Sequoia video second-level batch trace: PASS");
}
