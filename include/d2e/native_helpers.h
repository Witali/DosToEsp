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
void d2e_native_helper_mul16(d2e_x86_cpu *cpu, uint16_t operand);

#ifdef __cplusplus
}
#endif

#endif
