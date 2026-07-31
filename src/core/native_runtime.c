#include "d2e/native_runtime.h"

#include <string.h>

static const d2e_native_block *find_block(const d2e_native_program *program,
                                          uint16_t ip) {
    size_t low = 0;
    size_t high = program->block_count;
    while (low < high) {
        const size_t middle = low + (high - low) / 2U;
        const uint16_t candidate = program->blocks[middle].ip;
        if (candidate < ip) {
            low = middle + 1U;
        } else {
            high = middle;
        }
    }
    if (low < program->block_count && program->blocks[low].ip == ip) {
        return &program->blocks[low];
    }
    return NULL;
}

int d2e_native_load_com(d2e_x86_cpu *cpu,
                        const d2e_native_program *program) {
    const uint32_t psp = d2e_x86_linear(program->load_segment, 0);
    const uint32_t image =
        d2e_x86_linear(program->load_segment, UINT16_C(0x0100));

    if (program->image_size > UINT16_C(0xff00) ||
        image + program->image_size > D2E_X86_MEMORY_SIZE) {
        return 0;
    }

    d2e_x86_cpu_reset(cpu);
    memset(cpu->memory + psp, 0, UINT16_C(0x0100));
    memcpy(cpu->memory + image, program->image, program->image_size);
    cpu->memory[psp] = UINT8_C(0xcd);
    cpu->memory[psp + 1U] = UINT8_C(0x20);
    cpu->segments[D2E_X86_CS] = program->load_segment;
    cpu->segments[D2E_X86_DS] = program->load_segment;
    cpu->segments[D2E_X86_ES] = program->load_segment;
    cpu->segments[D2E_X86_SS] = program->load_segment;
    cpu->regs[D2E_X86_SP] = UINT16_C(0xfffe);
    cpu->ip = program->entry_ip;
    d2e_x86_write16_seg(cpu, program->load_segment, UINT16_C(0xfffe), 0);
    return 1;
}

d2e_x86_stop_reason d2e_native_run(d2e_x86_cpu *cpu,
                                   const d2e_native_program *program,
                                   uint32_t block_budget) {
    uint32_t block_count = 0;
    cpu->stop_reason = D2E_X86_RUNNING;
    while (cpu->stop_reason == D2E_X86_RUNNING &&
           block_count < block_budget) {
        const d2e_native_block *const block = find_block(program, cpu->ip);
        if (cpu->segments[D2E_X86_CS] != program->load_segment ||
            block == NULL) {
            cpu->fault_cs = cpu->segments[D2E_X86_CS];
            cpu->fault_ip = cpu->ip;
            cpu->stop_reason = D2E_X86_UNTRANSLATED_TARGET;
            break;
        }
        block->function(cpu);
        ++block_count;
    }
    if (cpu->stop_reason == D2E_X86_RUNNING) {
        cpu->stop_reason = D2E_X86_BUDGET_EXHAUSTED;
    }
    return cpu->stop_reason;
}

void d2e_native_interrupt(d2e_x86_cpu *cpu, uint8_t interrupt_number) {
    if (interrupt_number == UINT8_C(0x20)) {
        cpu->exit_code = 0;
        cpu->stop_reason = D2E_X86_EXITED;
        return;
    }
    if (interrupt_number == UINT8_C(0x21) &&
        d2e_x86_get_reg8(cpu, 4U) == UINT8_C(0x4c)) {
        cpu->exit_code = d2e_x86_get_reg8(cpu, 0U);
        cpu->stop_reason = D2E_X86_EXITED;
        return;
    }
    cpu->fault_cs = cpu->segments[D2E_X86_CS];
    cpu->fault_ip = cpu->ip;
    cpu->stop_reason = D2E_X86_UNHANDLED_INTERRUPT;
}

