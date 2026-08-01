#include "d2e/native_patterns.h"

static uint16_t advance(const d2e_x86_cpu *cpu, uint16_t offset,
                        uint16_t width) {
    return (uint16_t)(offset +
                      ((cpu->flags & D2E_X86_FLAG_DF) != 0U
                           ? (uint16_t)(0U - width)
                           : width));
}

void d2e_pattern_copy8(d2e_x86_cpu *cpu, uint16_t source_segment,
                       uint16_t destination_segment, uint16_t *source_offset,
                       uint16_t *destination_offset, uint16_t *count) {
    while (*count != 0U) {
        const uint8_t value = d2e_x86_read8(
            cpu, d2e_x86_linear(source_segment, *source_offset));
        d2e_x86_write8(cpu,
                       d2e_x86_linear(destination_segment,
                                      *destination_offset),
                       value);
        if (cpu->stop_reason != D2E_X86_RUNNING) {
            return;
        }
        *source_offset = advance(cpu, *source_offset, UINT16_C(1));
        *destination_offset =
            advance(cpu, *destination_offset, UINT16_C(1));
        *count = (uint16_t)(*count - UINT16_C(1));
    }
}

void d2e_pattern_copy16(d2e_x86_cpu *cpu, uint16_t source_segment,
                        uint16_t destination_segment, uint16_t *source_offset,
                        uint16_t *destination_offset, uint16_t *count) {
    while (*count != 0U) {
        const uint16_t value =
            d2e_x86_read16_seg(cpu, source_segment, *source_offset);
        d2e_x86_write16_seg(cpu, destination_segment, *destination_offset,
                            value);
        if (cpu->stop_reason != D2E_X86_RUNNING) {
            return;
        }
        *source_offset = advance(cpu, *source_offset, UINT16_C(2));
        *destination_offset =
            advance(cpu, *destination_offset, UINT16_C(2));
        *count = (uint16_t)(*count - UINT16_C(1));
    }
}

void d2e_pattern_fill8(d2e_x86_cpu *cpu, uint16_t destination_segment,
                       uint16_t *destination_offset, uint16_t *count,
                       uint8_t value) {
    while (*count != 0U) {
        d2e_x86_write8(cpu,
                       d2e_x86_linear(destination_segment,
                                      *destination_offset),
                       value);
        if (cpu->stop_reason != D2E_X86_RUNNING) {
            return;
        }
        *destination_offset =
            advance(cpu, *destination_offset, UINT16_C(1));
        *count = (uint16_t)(*count - UINT16_C(1));
    }
}

void d2e_pattern_fill16(d2e_x86_cpu *cpu, uint16_t destination_segment,
                        uint16_t *destination_offset, uint16_t *count,
                        uint16_t value) {
    while (*count != 0U) {
        d2e_x86_write16_seg(cpu, destination_segment, *destination_offset,
                            value);
        if (cpu->stop_reason != D2E_X86_RUNNING) {
            return;
        }
        *destination_offset =
            advance(cpu, *destination_offset, UINT16_C(2));
        *count = (uint16_t)(*count - UINT16_C(1));
    }
}
