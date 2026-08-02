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

uint16_t d2e_native_helper_read16(const d2e_x86_cpu *cpu, uint16_t segment,
                                  uint16_t offset) {
    return d2e_x86_read16_seg(cpu, segment, offset);
}

uint8_t d2e_native_helper_read8(const d2e_x86_cpu *cpu, uint16_t segment,
                                uint16_t offset) {
    return d2e_x86_read8(cpu, d2e_x86_linear(segment, offset));
}

void d2e_native_helper_write16(d2e_x86_cpu *cpu, uint16_t segment,
                               uint16_t offset, uint16_t value) {
    d2e_x86_write16_seg(cpu, segment, offset, value);
}

void d2e_native_helper_write8(d2e_x86_cpu *cpu, uint16_t segment,
                              uint16_t offset, uint8_t value) {
    d2e_x86_write8(cpu, d2e_x86_linear(segment, offset), value);
}
