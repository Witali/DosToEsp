#ifndef D2E_NATIVE_RUNTIME_H
#define D2E_NATIVE_RUNTIME_H

#include "d2e/x86_cpu.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*d2e_native_block_fn)(d2e_x86_cpu *cpu);
typedef uint32_t (*d2e_native_region_fn)(d2e_x86_cpu *cpu,
                                         uint32_t block_budget);

typedef enum d2e_native_image_format {
    D2E_NATIVE_IMAGE_COM = 0,
    D2E_NATIVE_IMAGE_MZ = 1
} d2e_native_image_format;

typedef struct d2e_mz_relocation {
    uint16_t offset;
    uint16_t segment;
} d2e_mz_relocation;

typedef struct d2e_native_block {
    uint16_t ip;
    d2e_native_block_fn function;
} d2e_native_block;

typedef struct d2e_native_program {
    const char *name;
    d2e_native_image_format format;
    uint16_t load_segment;
    uint16_t entry_cs;
    uint16_t entry_ip;
    uint16_t initial_ss;
    uint16_t initial_sp;
    const uint8_t *image;
    size_t image_size;
    const d2e_mz_relocation *relocations;
    size_t relocation_count;
    const d2e_native_block *blocks;
    size_t block_count;
    d2e_native_region_fn region;
} d2e_native_program;

int d2e_native_load_com(d2e_x86_cpu *cpu,
                        const d2e_native_program *program);
int d2e_native_load_mz(d2e_x86_cpu *cpu,
                       const d2e_native_program *program);
d2e_x86_stop_reason d2e_native_run(d2e_x86_cpu *cpu,
                                   const d2e_native_program *program,
                                   uint32_t block_budget);
void d2e_native_interrupt(d2e_x86_cpu *cpu, uint8_t interrupt_number);

#ifdef __cplusplus
}
#endif

#endif
