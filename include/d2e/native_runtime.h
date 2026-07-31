#ifndef D2E_NATIVE_RUNTIME_H
#define D2E_NATIVE_RUNTIME_H

#include "d2e/x86_cpu.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*d2e_native_block_fn)(d2e_x86_cpu *cpu);

typedef struct d2e_native_block {
    uint16_t ip;
    d2e_native_block_fn function;
} d2e_native_block;

typedef struct d2e_native_program {
    const char *name;
    uint16_t load_segment;
    uint16_t entry_ip;
    const uint8_t *image;
    size_t image_size;
    const d2e_native_block *blocks;
    size_t block_count;
} d2e_native_program;

int d2e_native_load_com(d2e_x86_cpu *cpu,
                        const d2e_native_program *program);
d2e_x86_stop_reason d2e_native_run(d2e_x86_cpu *cpu,
                                   const d2e_native_program *program,
                                   uint32_t block_budget);
void d2e_native_interrupt(d2e_x86_cpu *cpu, uint8_t interrupt_number);

#ifdef __cplusplus
}
#endif

#endif

