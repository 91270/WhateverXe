#include "kern_tgl_display_wake_pwm.hpp"
#include <cassert>
#include <cstdint>
int main(){
 using namespace TGLDisplayWakePWM;
 // Reproduced failure: PG1 is distributed with bit 26, while bit 24
 // (PG3) is clear. The older guard incorrectly skipped PWM repair.
 assert(pg1Ready(3U,0x8C000000U));
 assert(!pg1Ready(3U,0x88000000U));
 assert(!pg1Ready(0U,0x8C000000U));
 assert(!pg1Ready(Invalid,0x8C000000U));
 assert(!pg1Ready(3U,Invalid));
 static_assert(pg1Ready(3U,0x8C000000U),"PG1 not PG3");
 static_assert(!pg1Ready(3U,0x88000000U),"missing PG1 fuse");
 Readout good{1,2,2,0,17777,17741,0x80000000U,65535,true,true,true};
 assert(rearm(good));
 assert(enabledControl(good)==PWMEnable);
 auto q=good;
 q.control=PWMPolarity;assert(rearm(q));assert(enabledControl(q)==(PWMEnable|PWMPolarity));
 q=good;q.priorState=2;assert(!rearm(q)); // no redundant wake
 q=good;q.priorState=0;assert(!rearm(q)); // system sleep has a different lifecycle
 q=good;q.requestedState=1;assert(!rearm(q));
 q=good;q.actualState=1;assert(!rearm(q));
 q=good;q.panelStatus=0;assert(!rearm(q)); // no panel power
 q=good;q.panelStatus=Invalid;assert(!rearm(q));
 q=good;q.control=PWMEnable;assert(!rearm(q)); // enabled and nonzero duty
 q=good;q.control=Invalid;assert(!rearm(q)); // MMIO not accessible
 q=good;q.control=0x40000000U;assert(!rearm(q)); // nonstandard control
 q=good;q.duty=0;assert(rearm(q));assert(restoreDutyRequired(q));
 assert(restoredDuty(q)==q.period);
 q.nativeBrightness=32768;assert(restoredDuty(q)>0 && restoredDuty(q)<q.period);
 q.nativeBrightness=0;assert(!rearm(q));
 // A deliberately dark system brightness must not be overwritten by
 // previously valid hardware duty, even when the donor PWM is still nonzero.
 q=good;q.maximumBrightness=1024;q.requestedBrightness=0;assert(!rearm(q));
 q.requestedBrightness=1024;assert(rearm(q));
 q=good;q.maximumBrightness=UINT32_MAX;q.requestedBrightness=1;assert(!rearm(q));
 // Native brightness cache is cleared on Doze: resume using the authenticated
 // pre-Doze PWM level for this exact framebuffer epoch, not an arbitrary level.
 q=good;q.duty=0;q.nativeBrightness=0;
 q.preDozeDuty=17741;assert(!rearm(q)); // no proof of requested brightness
 q.requestedBrightness=1024;q.maximumBrightness=1024;
 assert(userWantsLight(q));assert(rearm(q));assert(restoreDutyRequired(q));
 assert(restoredDuty(q)==17741);
 // The native PWM can be enabled while its duty is still zero.
 q.control=PWMEnable;assert(rearm(q));assert(enabledControl(q)==PWMEnable);
 // Never re-light a user-intended zero-brightness display.
 q.requestedBrightness=0;assert(!userWantsLight(q));assert(!rearm(q));
 q.requestedBrightness=1025;assert(!rearm(q));
 q.requestedBrightness=1024;q.preDozeDuty=17778;assert(!rearm(q));
 q.preDozeDuty=0;assert(!rearm(q));
 q=good;q.period=0;assert(!rearm(q));
 q=good;q.duty=17778;assert(!rearm(q));
 q=good;q.period=Invalid;assert(!rearm(q));
 q=good;q.qualified=false;assert(!rearm(q));
 q=good;q.powerReady=false;assert(!rearm(q));
 q=good;q.independentPWM=false;assert(!rearm(q)); // DPCD/adapter-owned
 static_assert(rearm(Readout{1,2,2,0,17777,17741,0x80000000U,65535,true,true,true}),"positive");
 static_assert(!rearm(Readout{1,2,2,0,17777,0,0x80000000U,0,true,true,true}),"skip zero");
}
