// Experimental Sequoia recovery gate. Opt-in only: no change on existing boots.
#ifndef KERN_TGL_RECOVERY_GATE_HPP
#define KERN_TGL_RECOVERY_GATE_HPP
#include "kern_xelp_os.hpp"

namespace TGLRecoveryGate {
inline bool requested(XELP::OS os,bool disableGraphicsFirmware,bool sequoiaOptIn) {
    return disableGraphicsFirmware &&
        (os==XELP::OS::BigSur || os==XELP::OS::Tahoe ||
         (os==XELP::OS::Sequoia && sequoiaOptIn));
}
}
#endif
