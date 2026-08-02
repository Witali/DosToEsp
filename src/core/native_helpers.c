#include "d2e/native_helpers.h"

#include "d2e/x86_alu.h"

void d2e_native_helper_mul16(d2e_x86_cpu *cpu, uint16_t operand,
                             uint16_t live_flags) {
    const uint32_t result = (live_flags &
                             (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF)) != 0U
                                ? d2e_x86_mul16(
                                      cpu, cpu->regs[D2E_X86_AX], operand)
                                : (uint32_t)cpu->regs[D2E_X86_AX] * operand;
    cpu->regs[D2E_X86_AX] = (uint16_t)result;
    cpu->regs[D2E_X86_DX] = (uint16_t)(result >> 16U);
}
