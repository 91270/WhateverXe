// Tiger Lake eDP Display-Doze wake: fail-closed PWM re-arm qualification.
// These state predicates intentionally do not imply panel power ownership.
#ifndef kern_tgl_display_wake_pwm_hpp
#define kern_tgl_display_wake_pwm_hpp
#include <stdint.h>
namespace TGLDisplayWakePWM {
constexpr uint32_t Invalid = UINT32_MAX;
constexpr uint32_t PWMEnable = 0x80000000U;
constexpr uint32_t PWMPolarity = 0x20000000U;
constexpr uint32_t PanelOn = 0x80000000U;
// Intel i915: SKL_FUSE_PG_DIST_STATUS(SKL_PG1) = 1 << (27 - 1).
// Bit 24 is PG3, not PG1; a PG1 owner must never be gated by PG3.
constexpr uint32_t PG1FuseDistributed = 0x04000000U;
// HSW_PWR_WELL_CTL_STATE(ICL_PW_CTL_IDX_PW_1) = 1 << (2 * 0).
constexpr uint32_t PG1PowerWellState = 0x00000001U;
constexpr bool pg1Ready(uint32_t wells,uint32_t fuse) {
 return wells!=Invalid && fuse!=Invalid &&
        (wells & PG1PowerWellState) && (fuse & PG1FuseDistributed);
}
struct Readout {
 uint32_t priorState {},requestedState {},actualState {};
 uint32_t control {Invalid},period {Invalid},duty {Invalid},panelStatus {Invalid};
 uint32_t nativeBrightness {};
 bool qualified {},powerReady {},independentPWM {};
 // Captured before native Wake->Doze under native PG1, same FB/controller/period.
 uint32_t preDozeDuty {};
 // Independent IOBacklightDisplay brightness. A donor cache of zero does
 // not mean the user explicitly requested zero while the display is asleep.
 uint32_t requestedBrightness {},maximumBrightness {};
};
constexpr bool userWantsLight(const Readout &p) {
 return p.maximumBrightness>0 && p.maximumBrightness!=Invalid &&
        p.requestedBrightness>0 && p.requestedBrightness<=p.maximumBrightness;
}
// Native hwSetBacklight stores the user's last level at controller+0xe58,
// but display doze can clear the PWM duty without changing that field.
// Restore duty only when native level is known and not zero. Never create
// brightness for an intentionally dark display.
constexpr uint32_t restoredDuty(const Readout &p) {
 if (p.period==0 || p.period==Invalid)return 0;
 // If the system brightness property is present and explicitly zero,
 // no stale donor or PWM receipt may re-light the panel.
 if (p.maximumBrightness && !userWantsLight(p))return 0;
 if (p.duty!=Invalid && p.duty>0 && p.duty<=p.period)return p.duty;
 if (p.duty==0 && p.nativeBrightness>0 && p.nativeBrightness<=65535)
  return static_cast<uint32_t>((static_cast<uint64_t>(p.period)*p.nativeBrightness)/65535U);
 if (p.duty==0 && userWantsLight(p) &&
     p.preDozeDuty>0 && p.preDozeDuty<=p.period)
  return p.preDozeDuty;
 return 0;
}
constexpr bool restoreDutyRequired(const Readout &p) {
 return p.duty==0 && restoredDuty(p)>0;
}
constexpr bool rearm(const Readout &p) {
 return p.qualified && p.powerReady && p.independentPWM &&
        p.priorState==1 && p.requestedState==2 && p.actualState==2 &&
        p.panelStatus!=Invalid && (p.panelStatus & PanelOn) &&
        p.control!=Invalid &&
        !(p.control & ~(PWMPolarity | PWMEnable)) &&
        p.period!=0 && p.period!=Invalid &&
        p.duty!=Invalid && (p.duty==0 || p.duty<=p.period) &&
        restoredDuty(p)>0 &&
        (!(p.control & PWMEnable) || restoreDutyRequired(p));
}
constexpr uint32_t enabledControl(const Readout &p) {
 return p.control | PWMEnable;
}
}
#endif
