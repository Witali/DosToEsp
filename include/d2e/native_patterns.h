#ifndef D2E_NATIVE_PATTERNS_H
#define D2E_NATIVE_PATTERNS_H

#include "d2e/x86_cpu.h"

#ifdef __cplusplus
extern "C" {
#endif

void d2e_pattern_copy8(d2e_x86_cpu *cpu, uint16_t source_segment,
                       uint16_t destination_segment, uint16_t *source_offset,
                       uint16_t *destination_offset, uint16_t *count);
void d2e_pattern_copy16(d2e_x86_cpu *cpu, uint16_t source_segment,
                        uint16_t destination_segment, uint16_t *source_offset,
                        uint16_t *destination_offset, uint16_t *count);
void d2e_pattern_fill8(d2e_x86_cpu *cpu, uint16_t destination_segment,
                       uint16_t *destination_offset, uint16_t *count,
                       uint8_t value);
void d2e_pattern_fill16(d2e_x86_cpu *cpu, uint16_t destination_segment,
                        uint16_t *destination_offset, uint16_t *count,
                        uint16_t value);

#ifdef __cplusplus
}
#endif

#endif
