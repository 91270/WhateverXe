#include "../WhateverXe/kern_tgl_recovery_gate.hpp"
#include <cassert>
#include <cstdio>
#include <initializer_list>
int main() {
    using XELP::OS;
    const OS versions[]={
        OS::Unknown,OS::Donor,OS::BigSur,OS::Monterey,OS::Ventura,
        OS::Sonoma,OS::Sequoia,OS::Tahoe
    };
    unsigned cases=0;
    for (const OS os:versions)
        for (const bool disable:{false,true})
            for (const bool optin:{false,true}) {
                const bool expected=disable &&
                    (os==OS::BigSur || os==OS::Tahoe ||
                     (os==OS::Sequoia && optin));
                assert(TGLRecoveryGate::requested(os,disable,optin)==expected);
                ++cases;
            }
    // Default Sequoia boot is unchanged, even with -disablegfxfirmware.
    assert(!TGLRecoveryGate::requested(OS::Sequoia,true,false));
    // Manual test opt-in requires both flags.
    assert(!TGLRecoveryGate::requested(OS::Sequoia,false,true));
    assert(TGLRecoveryGate::requested(OS::Sequoia,true,true));
    std::printf("%u guarded recovery-policy cases passed\n",cases);
}
