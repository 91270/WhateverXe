#!/usr/bin/env python3
"""Compile and test the actual passive PPS/HPD observer code in userspace.
No IOKit/real GPU/MMIO access. Sanitizers detect memory/locking errors.
"""
from pathlib import Path
import re
import subprocess
import tempfile

repo=Path(__file__).resolve().parents[1]
src=(repo/"WhateverXe/kern_xe.cpp").read_text()
header=re.search(r"struct TGLAUXNativeMMIO \{.*?\n\};",src,re.S)
body=re.search(r"constexpr size_t tglEDPPanelSlots=6;.*?(?=static void tglEDPAUXNativeMMIORecord)",src,re.S)
aux=re.search(r"static void tglEDPAUXNativeMMIORecord\(.*?\n\}",src,re.S)
first=re.search(r"struct TGLAUXFirstCommandWitness \{.*?(?=static bool tglEDPAUXNativeMMIOSerialize)",src,re.S)
state=re.search(r"// Sticky first-AUX command identity.*?\nstatic uint32_t tglEDPAUXRecentData1Count\{\};",src,re.S)
assert first and state
assert header and body and aux
for check in (
    "tglEDPPanelNativeMMIORecord(access,reg,false,value,",
    "tglEDPPanelNativeMMIORecord(access,reg,true,value,",
    "WhateverXeEDPPanelNativeMMIO",
    "WhateverXeEDPPanelPreAUX",
    "tglEDPPanelMMIOEpochCount=0;",
    "bzero(tglEDPPanelLatest,sizeof(tglEDPPanelLatest));",
    "tglEDPPanelFirstAUXNS=0;",
):
    assert check in src,check

fixture=r"""
#include <cstdint>
#include <cstddef>
#include <cstdlib>
#include <cstring>
#include <cassert>
#include <vector>
#include <cstdio>
template<class T,size_t N> constexpr size_t arrsize(const T (&)[N]){return N;}
struct OSSerialize {std::vector<uint8_t> bytes;};
bool locked=false,failAlloc=false,failData=false;
struct IOSimpleLock {};
IOSimpleLock auxLock,*tglAUXLock=&auxLock;
int IOSimpleLockLockDisableInterrupt(IOSimpleLock *l) {
  assert(l==tglAUXLock&&!locked);locked=true;return 4;
}
void IOSimpleLockUnlockEnableInterrupt(IOSimpleLock *l,int f) {
  assert(l==tglAUXLock&&f==4&&locked);locked=false;
}
void *IOMalloc(size_t n) {assert(!locked);return failAlloc?nullptr:malloc(n);}
void IOFree(void *p,size_t) {assert(!locked);free(p);}
struct OSData {
  std::vector<uint8_t> bytes;
  static OSData *withBytes(const void *raw,size_t n) {
    assert(!locked);
    if(failData)return nullptr;
    auto p=new OSData;
    p->bytes.assign((const uint8_t*)raw,(const uint8_t*)raw+n);
    return p;
  }
  bool serialize(OSSerialize *out) {assert(!locked);out->bytes=bytes;return true;}
  void release() {assert(!locked);delete this;}
};
uint64_t ticks=0;
void clock_get_uptime(uint64_t *p) {*p=++ticks;}
void absolutetime_to_nanoseconds(uint64_t time,uint64_t *p){*p=time;}
uintptr_t currentThreadToken=0x12345678;
void *current_thread(){return reinterpret_cast<void *>(currentThreadToken);}
uint32_t tglConnectionCaller(void *){return 0x1234;}
uint32_t tglEDPAUXWakeEpoch=0;
///PRODUCTION_TYPE
static TGLAUXNativeMMIO tglEDPAUXMMIOFirst[64]{},tglEDPAUXMMIOLast[256]{};
static uint32_t tglEDPAUXMMIOCount{},tglEDPAUXMMIOEpochCount{};
///PRODUCTION_STATE
///PRODUCTION_PANEL
///PRODUCTION_AUX
///PRODUCTION_FIRST
alignas(8) uint8_t controller[0xC80]{};
int fakeAccess1=7, fakeAccess2=8;
void *access=&fakeAccess1;
void putRead(uint32_t reg,uint32_t val,bool diag=true) {
  tglEDPPanelNativeMMIORecord(access,reg,false,val,(void*)0x999,diag,controller);
}
void putWrite(uint32_t reg,uint32_t val,bool diag=true) {
  tglEDPPanelNativeMMIORecord(access,reg,true,val,(void*)0x999,diag,controller);
}
void firstAUX(uint32_t val=0x8c60023f) {
  tglEDPAUXNativeMMIORecord(access,0x64014,true,0x91020200,(void*)0x999,true,controller);
  tglEDPAUXNativeMMIORecord(access,0x64010,true,val,(void*)0x999,true,controller);
}
TGLAUXFirstCommandWitness firstCommand() {
  OSSerialize x;
  assert(tglEDPAUXFirstCommandSerialize(nullptr,nullptr,&x));
  assert(x.bytes.size()==sizeof(TGLAUXFirstCommandWitness));
  TGLAUXFirstCommandWitness out{};
  memcpy(&out,x.bytes.data(),sizeof(out));
  return out;
}
TGLPanelPreAUXWitness pre() {
  OSSerialize a;
  assert(tglEDPPanelPreAUXSerialize(nullptr,nullptr,&a));
  assert(a.bytes.size()==sizeof(TGLPanelPreAUXWitness));
  TGLPanelPreAUXWitness out{};
  memcpy(&out,a.bytes.data(),sizeof(out));
  return out;
}
void freshWake() {
  ++tglEDPAUXWakeEpoch;
  tglEDPAUXMMIOEpochCount=0;
  bzero(tglEDPAUXMMIOFirst,sizeof(tglEDPAUXMMIOFirst));
  tglEDPPanelMMIOEpochCount=0;
  bzero(tglEDPPanelMMIOFirst,sizeof(tglEDPPanelMMIOFirst));
  bzero(tglEDPPanelLatest,sizeof(tglEDPPanelLatest));
  bzero(tglEDPPanelPreAUX,sizeof(tglEDPPanelPreAUX));
  tglEDPPanelPreAUXValid=0;
  tglEDPPanelFirstAUXEpoch=0;
  tglEDPPanelFirstAUXSeq=0;
  tglEDPPanelFirstAUXNS=0;
  bzero(tglEDPAUXRecentData1,sizeof(tglEDPAUXRecentData1));
  tglEDPAUXRecentData1Count=0;
  tglEDPAUXFirstCtl={};
  tglEDPAUXFirstData1={};
}
int main() {
  *reinterpret_cast<void**>(controller+0xC40)=access;
  auto first=pre();
  assert(first.validMask==0 && first.auxEpoch==0);
  // Disabled, unknown register or wrong-owner manager do not record anything.
  putRead(0xC7200,0x80000000,false);
  putRead(0xDEAD,777);
  tglEDPPanelNativeMMIORecord(&fakeAccess2,0xC7200,false,8,nullptr,true,controller);
  assert(tglEDPPanelMMIOCount==0);
  freshWake();assert(tglEDPAUXWakeEpoch==1);
  putRead(0xC7200,0x80000000);
  putWrite(0xC7204,0x00000008); // Request, not committed ACK.
  putRead(0xC4000,0x00010000);
  putRead(0xC7208,0x12345678);
  putRead(0xC720C,0x87654321);
  auto noAux=pre();
  assert(noAux.epoch==1 && noAux.auxEpoch==0 && noAux.validMask==0);
  firstAUX();
  auto snap=pre();
  assert(snap.epoch==1 && snap.auxEpoch==1 && snap.auxSequence==2);
  auto firstCmd=firstCommand();
  assert(firstCmd.version==1 && firstCmd.epoch==1 && firstCmd.auxValid==1 && firstCmd.dataValid==1);
  assert(firstCmd.auxCtl.word[3]==0x64010 && firstCmd.auxCtl.word[4]==0x8c60023f);
  assert(firstCmd.data1.word[3]==0x64014 && firstCmd.data1.word[4]==0x91020200);
  assert(snap.validMask==0x1f && snap.firstAuxNS>snap.last[4].ns);
  assert(snap.last[0].word[3]==0xC7200 && snap.last[0].word[4]==0x80000000);
  assert(snap.last[1].word[3]==0xC7204 && snap.last[1].word[4]==8 && snap.last[1].word[2]==1);
  assert(snap.last[4].word[3]==0xC4000 && snap.last[4].word[4]==0x00010000);
  assert(snap.last[5].word[0]==0); // Missing: do NOT claim HPD good.
  putRead(0xC7200,0x00000000); // Post-AUX must not rewrite frozen snapshot.
  putRead(0x44470,0xffffffff);
  firstAUX();
  auto frozen=pre();
  assert(frozen.validMask==0x1f && frozen.last[0].word[4]==0x80000000);
  assert(frozen.last[5].word[0]==0 && frozen.auxSequence==snap.auxSequence);
  assert(tglEDPPanelMMIOCount==7);
  // Separate ring has 64 first samples and 128 most recent; AUX storm cannot evict.
  for(unsigned i=0;i<350;++i)firstAUX();
  assert(tglEDPPanelMMIOCount==7 && tglEDPAUXMMIOCount==704);
  assert(tglEDPAUXMMIOFirst[0].word[3]==0x64014 && tglEDPAUXMMIOFirst[0].word[4]==0x91020200);
  assert(tglEDPAUXMMIOFirst[1].word[3]==0x64010 && tglEDPAUXMMIOFirst[1].word[4]==0x8c60023f);
  firstCmd=firstCommand();
  assert(firstCmd.epoch==1 && firstCmd.auxValid && firstCmd.dataValid);
  assert(firstCmd.data1.word[0]==1 && firstCmd.auxCtl.word[0]==2);
  for(unsigned i=0;i<190;++i)putRead(0xC7200,i);
  OSSerialize out;
  assert(tglEDPPanelNativeMMIOSerialize(nullptr,nullptr,&out));
  assert(out.bytes.size()==16+(64+128)*sizeof(TGLAUXNativeMMIO));
  uint32_t words[4];memcpy(words,out.bytes.data(),16);
  assert(words[0]==1 && words[1]==197 && words[2]==64 && words[3]==48);
  TGLAUXNativeMMIO firstEntry{};
  memcpy(&firstEntry,out.bytes.data()+16,48);
  assert(firstEntry.word[0]==1 && firstEntry.word[3]==0xC7200);
  TGLAUXNativeMMIO latest{};
  const uint32_t finalSeq=tglEDPPanelMMIOCount;
  const size_t ringOffset=16+64*48+((finalSeq-1)%128)*48;
  memcpy(&latest,out.bytes.data()+ringOffset,48);
  assert(latest.word[0]==finalSeq && latest.word[4]==189);
  assert(pre().last[0].word[4]==0x80000000);
  failAlloc=true;assert(!tglEDPPanelNativeMMIOSerialize(nullptr,nullptr,&out));failAlloc=false;
  failData=true;
  assert(!tglEDPPanelNativeMMIOSerialize(nullptr,nullptr,&out));
  assert(!tglEDPPanelPreAUXSerialize(nullptr,nullptr,&out));
  assert(!tglEDPAUXFirstCommandSerialize(nullptr,nullptr,&out));
  failData=false;
  // New epoch starts with no inherited PPS/HPD witness.
  freshWake();
  firstAUX();
  snap=pre();
  assert(snap.epoch==2 && snap.auxEpoch==2 && snap.validMask==0);
  for(const auto &item:snap.last)assert(item.word[0]==0);
  firstCmd=firstCommand();
  assert(firstCmd.epoch==2 && firstCmd.auxValid && firstCmd.dataValid);
  freshWake();
  tglEDPAUXNativeMMIORecord(access,0x64010,true,0x8c60023f,(void*)0x999,true,controller);
  firstCmd=firstCommand();
  assert(firstCmd.epoch==3 && firstCmd.auxValid==1 && firstCmd.dataValid==0);
  // Two same-epoch AUX threads may interleave their DATA1 writes before
  // native SEND. The wrong-thread newest header must not mask the right one.
  freshWake();
  tglEDPAUXNativeMMIORecord(access,0x64014,true,0x80010001,(void*)0x999,true,controller);
  currentThreadToken=0x87654321;
  tglEDPAUXNativeMMIORecord(access,0x64014,true,0x80020201,(void*)0x999,true,controller);
  currentThreadToken=0x12345678;
  tglEDPAUXNativeMMIORecord(access,0x64010,true,0x8c60023f,(void*)0x999,true,controller);
  firstCmd=firstCommand();
  assert(firstCmd.epoch==4 && firstCmd.auxValid==1 && firstCmd.dataValid==1);
  assert(firstCmd.data1.word[4]==0x80010001 &&
         firstCmd.data1.thread==firstCmd.auxCtl.thread);
  // Fail closed when the same-thread header was evicted by other threads.
  freshWake();
  tglEDPAUXNativeMMIORecord(access,0x64014,true,0x80010001,(void*)0x999,true,controller);
  currentThreadToken=0x87654321;
  for(unsigned i=0;i<32;++i)
    tglEDPAUXNativeMMIORecord(access,0x64014,true,0x80020201,(void*)0x999,true,controller);
  currentThreadToken=0x12345678;
  tglEDPAUXNativeMMIORecord(access,0x64010,true,0x8c60023f,(void*)0x999,true,controller);
  firstCmd=firstCommand();
  assert(firstCmd.epoch==5 && firstCmd.auxValid==1 && firstCmd.dataValid==0);

  assert(!locked);
  std::puts("PASS: production PPS/HPD recorder & serialization, first AUX latch, absent-value semantics, independent ring, wrong-access guards, failure cleanup, epoch reset");
}
"""
out=(fixture.replace("///PRODUCTION_TYPE",header.group()).replace("///PRODUCTION_STATE",state.group()).replace("///PRODUCTION_PANEL",body.group()).replace("///PRODUCTION_AUX",aux.group()).replace("///PRODUCTION_FIRST",first.group()))
assert "///PRODUCTION" not in out
with tempfile.TemporaryDirectory(prefix="tgl-edp-panel-observer-") as tmp:
    p=Path(tmp)
    (p/"test.cpp").write_text(out)
    subprocess.run(["clang++","-std=c++14","-O1","-g","-fsanitize=address,undefined",
                    "-fno-omit-frame-pointer",str(p/"test.cpp"),"-o",str(p/"test")],check=True)
    subprocess.run([str(p/"test")],check=True)
