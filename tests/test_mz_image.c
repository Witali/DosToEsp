#include "d2e/native_runtime.h"

#include <stdio.h>
#include <stdlib.h>

extern const d2e_native_program d2e_generated_mz_program;

int main(void) {
    const d2e_native_program *const program = &d2e_generated_mz_program;
    const size_t memory_size = UINT32_C(128) * 1024U;
    uint8_t *const memory = calloc(memory_size, 1);
    d2e_x86_cpu cpu;
    size_t index;
    int failed = 0;

    if (memory == NULL) {
        return 2;
    }
    d2e_x86_cpu_init(&cpu, memory, memory_size, NULL);
    if (!d2e_native_load_mz(&cpu, program)) {
        fprintf(stderr, "generated MZ image load failed\n");
        failed = 1;
    } else if (cpu.segments[D2E_X86_CS] !=
                   (uint16_t)(program->load_segment + program->entry_cs) ||
               cpu.ip != program->entry_ip ||
               cpu.segments[D2E_X86_SS] !=
                   (uint16_t)(program->load_segment + program->initial_ss) ||
               cpu.regs[D2E_X86_SP] != program->initial_sp ||
               cpu.segments[D2E_X86_DS] !=
                   (uint16_t)(program->load_segment - UINT16_C(0x0010)) ||
               cpu.segments[D2E_X86_ES] != cpu.segments[D2E_X86_DS]) {
        fprintf(stderr, "generated MZ initial state is incorrect\n");
        failed = 1;
    }
    for (index = 0; !failed && index < program->relocation_count; ++index) {
        const d2e_mz_relocation *const relocation = &program->relocations[index];
        const uint32_t module_offset =
            (uint32_t)relocation->segment * UINT32_C(16) + relocation->offset;
        const uint32_t address =
            d2e_x86_linear(program->load_segment, 0) + module_offset;
        const uint16_t original =
            (uint16_t)(program->image[module_offset] |
                       ((uint16_t)program->image[module_offset + 1U] << 8U));
        const uint16_t loaded =
            (uint16_t)(memory[address] | ((uint16_t)memory[address + 1U] << 8U));
        if (loaded != (uint16_t)(original + program->load_segment)) {
            fprintf(stderr, "relocation %u is incorrect\n", (unsigned)index);
            failed = 1;
        }
    }
    free(memory);
    if (failed) {
        return 1;
    }
    printf("generated MZ image test passed: %u bytes, %u relocations\n",
           (unsigned)program->image_size, (unsigned)program->relocation_count);
    return 0;
}
