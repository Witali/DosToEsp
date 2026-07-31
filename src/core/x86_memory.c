#include "d2e/x86_cpu.h"

static uint32_t wrap_address(uint32_t address) {
    return address & D2E_X86_ADDRESS_MASK;
}

static void mark_write(d2e_x86_cpu *cpu, uint32_t address) {
    if (cpu->page_generations != NULL) {
        ++cpu->page_generations[wrap_address(address) >> D2E_X86_PAGE_SHIFT];
    }
}

uint32_t d2e_x86_linear(uint16_t segment, uint16_t offset) {
    return (((uint32_t)segment << 4U) + (uint32_t)offset) &
           D2E_X86_ADDRESS_MASK;
}

uint8_t d2e_x86_read8(const d2e_x86_cpu *cpu, uint32_t address) {
    return cpu->memory[wrap_address(address)];
}

uint16_t d2e_x86_read16(const d2e_x86_cpu *cpu, uint32_t address) {
    const uint8_t low = d2e_x86_read8(cpu, address);
    const uint8_t high = d2e_x86_read8(cpu, address + 1U);
    return (uint16_t)((uint16_t)low | ((uint16_t)high << 8U));
}

void d2e_x86_write8(d2e_x86_cpu *cpu, uint32_t address, uint8_t value) {
    const uint32_t wrapped = wrap_address(address);
    cpu->memory[wrapped] = value;
    mark_write(cpu, wrapped);
}

void d2e_x86_write16(d2e_x86_cpu *cpu, uint32_t address, uint16_t value) {
    d2e_x86_write8(cpu, address, (uint8_t)value);
    d2e_x86_write8(cpu, address + 1U, (uint8_t)(value >> 8U));
}

uint16_t d2e_x86_read16_seg(const d2e_x86_cpu *cpu, uint16_t segment,
                            uint16_t offset) {
    const uint8_t low = d2e_x86_read8(cpu, d2e_x86_linear(segment, offset));
    const uint8_t high = d2e_x86_read8(
        cpu, d2e_x86_linear(segment, (uint16_t)(offset + 1U)));
    return (uint16_t)((uint16_t)low | ((uint16_t)high << 8U));
}

void d2e_x86_write16_seg(d2e_x86_cpu *cpu, uint16_t segment, uint16_t offset,
                         uint16_t value) {
    d2e_x86_write8(cpu, d2e_x86_linear(segment, offset), (uint8_t)value);
    d2e_x86_write8(cpu,
                   d2e_x86_linear(segment, (uint16_t)(offset + 1U)),
                   (uint8_t)(value >> 8U));
}
