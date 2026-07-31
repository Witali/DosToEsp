#include "d2e/x86_cpu.h"

#include <string.h>

void d2e_x86_cpu_init(d2e_x86_cpu *cpu, uint8_t *memory,
                      uint32_t *page_generations) {
    memset(cpu, 0, sizeof(*cpu));
    cpu->memory = memory;
    cpu->page_generations = page_generations;
    d2e_x86_cpu_reset(cpu);
}

void d2e_x86_cpu_reset(d2e_x86_cpu *cpu) {
    uint8_t *const memory = cpu->memory;
    uint32_t *const page_generations = cpu->page_generations;

    memset(cpu, 0, sizeof(*cpu));
    cpu->memory = memory;
    cpu->page_generations = page_generations;
    cpu->flags = D2E_X86_FLAG_FIXED;
    cpu->stop_reason = D2E_X86_RUNNING;
}

uint8_t d2e_x86_get_reg8(const d2e_x86_cpu *cpu, unsigned encoded_reg) {
    const unsigned word_index = encoded_reg & 3U;
    const unsigned shift = (encoded_reg & 4U) != 0U ? 8U : 0U;
    return (uint8_t)(cpu->regs[word_index] >> shift);
}

void d2e_x86_set_reg8(d2e_x86_cpu *cpu, unsigned encoded_reg, uint8_t value) {
    const unsigned word_index = encoded_reg & 3U;
    const unsigned shift = (encoded_reg & 4U) != 0U ? 8U : 0U;
    const uint16_t mask = (uint16_t)(UINT16_C(0xff) << shift);
    cpu->regs[word_index] =
        (uint16_t)((cpu->regs[word_index] & (uint16_t)~mask) |
                   ((uint16_t)value << shift));
}

uint8_t d2e_x86_fetch8(const d2e_x86_cpu *cpu, uint16_t relative_ip) {
    const uint16_t offset = (uint16_t)(cpu->ip + relative_ip);
    return d2e_x86_read8(
        cpu, d2e_x86_linear(cpu->segments[D2E_X86_CS], offset));
}

uint16_t d2e_x86_fetch16(const d2e_x86_cpu *cpu, uint16_t relative_ip) {
    const uint16_t offset = (uint16_t)(cpu->ip + relative_ip);
    return d2e_x86_read16_seg(cpu, cpu->segments[D2E_X86_CS], offset);
}

void d2e_x86_push16(d2e_x86_cpu *cpu, uint16_t value) {
    cpu->regs[D2E_X86_SP] = (uint16_t)(cpu->regs[D2E_X86_SP] - 2U);
    d2e_x86_write16_seg(cpu, cpu->segments[D2E_X86_SS],
                        cpu->regs[D2E_X86_SP], value);
}

uint16_t d2e_x86_pop16(d2e_x86_cpu *cpu) {
    const uint16_t value =
        d2e_x86_read16_seg(cpu, cpu->segments[D2E_X86_SS],
                           cpu->regs[D2E_X86_SP]);
    cpu->regs[D2E_X86_SP] = (uint16_t)(cpu->regs[D2E_X86_SP] + 2U);
    return value;
}
