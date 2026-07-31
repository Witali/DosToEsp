#include "d2e/x86_cpu.h"

#include <string.h>

void d2e_x86_cpu_init(d2e_x86_cpu *cpu, uint8_t *memory, size_t memory_size,
                      uint32_t *page_generations) {
    memset(cpu, 0, sizeof(*cpu));
    cpu->memory = memory;
    cpu->memory_size = memory_size;
    cpu->page_generations = page_generations;
    d2e_x86_cpu_reset(cpu);
}

void d2e_x86_cpu_reset(d2e_x86_cpu *cpu) {
    uint8_t *const memory = cpu->memory;
    const size_t memory_size = cpu->memory_size;
    uint8_t *const cga_vram = cpu->cga_vram;
    uint32_t *const page_generations = cpu->page_generations;
    void *const port_context = cpu->port_context;
    const d2e_x86_port_in8_fn port_in8 = cpu->port_in8;
    const d2e_x86_port_out8_fn port_out8 = cpu->port_out8;

    memset(cpu, 0, sizeof(*cpu));
    cpu->memory = memory;
    cpu->memory_size = memory_size;
    cpu->cga_vram = cga_vram;
    cpu->page_generations = page_generations;
    cpu->port_context = port_context;
    cpu->port_in8 = port_in8;
    cpu->port_out8 = port_out8;
    cpu->flags = D2E_X86_FLAG_FIXED;
    cpu->stop_reason = D2E_X86_RUNNING;
}

void d2e_x86_map_cga_vram(d2e_x86_cpu *cpu, uint8_t *cga_vram) {
    cpu->cga_vram = cga_vram;
}

void d2e_x86_configure_ports(d2e_x86_cpu *cpu, void *context,
                             d2e_x86_port_in8_fn input,
                             d2e_x86_port_out8_fn output) {
    cpu->port_context = context;
    cpu->port_in8 = input;
    cpu->port_out8 = output;
}

uint8_t d2e_x86_port_in8(d2e_x86_cpu *cpu, uint16_t port) {
    uint8_t value = UINT8_C(0xff);
    if (cpu->port_in8 == NULL ||
        !cpu->port_in8(cpu->port_context, port, &value)) {
        cpu->fault_address = port;
        cpu->stop_reason = D2E_X86_UNHANDLED_PORT;
    }
    return value;
}

void d2e_x86_port_out8(d2e_x86_cpu *cpu, uint16_t port, uint8_t value) {
    if (cpu->port_out8 == NULL ||
        !cpu->port_out8(cpu->port_context, port, value)) {
        cpu->fault_address = port;
        cpu->stop_reason = D2E_X86_UNHANDLED_PORT;
    }
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
