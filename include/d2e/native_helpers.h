#ifndef D2E_NATIVE_HELPERS_H
#define D2E_NATIVE_HELPERS_H

#include "d2e/x86_cpu.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Generated assembly calls these functions through the normal ESP-IDF Xtensa
 * windowed ABI. Guest state is synchronized in `cpu` before each call. The
 * caller treats all ABI caller-saved registers and condition state as clobbered.
 */
void d2e_native_helper_mul16(d2e_x86_cpu *cpu, uint16_t operand,
                             uint16_t live_flags);
uint16_t d2e_native_helper_read16(const d2e_x86_cpu *cpu, uint16_t segment,
                                  uint16_t offset);
void d2e_native_helper_write16(d2e_x86_cpu *cpu, uint16_t segment,
                               uint16_t offset, uint16_t value);

#ifdef __cplusplus
}
#endif

#endif
