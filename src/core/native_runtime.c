#include "d2e/native_runtime.h"
#include "d2e/native_asm_offsets.h"

#include <stddef.h>
#include <string.h>

#if UINTPTR_MAX == UINT32_MAX
#define D2E_ASM_ABI_ASSERT(name, expression) \
    typedef char d2e_asm_abi_##name[(expression) ? 1 : -1]
D2E_ASM_ABI_ASSERT(cpu_regs,
                   offsetof(d2e_x86_cpu, regs) == D2E_ASM_CPU_REGS_OFFSET);
D2E_ASM_ABI_ASSERT(cpu_segments,
                   offsetof(d2e_x86_cpu, segments) ==
                       D2E_ASM_CPU_SEGMENTS_OFFSET);
D2E_ASM_ABI_ASSERT(cpu_ip,
                   offsetof(d2e_x86_cpu, ip) == D2E_ASM_CPU_IP_OFFSET);
D2E_ASM_ABI_ASSERT(cpu_stop_reason,
                   offsetof(d2e_x86_cpu, stop_reason) ==
                       D2E_ASM_CPU_STOP_REASON_OFFSET);
D2E_ASM_ABI_ASSERT(cpu_fault_cs,
                   offsetof(d2e_x86_cpu, fault_cs) ==
                       D2E_ASM_CPU_FAULT_CS_OFFSET);
D2E_ASM_ABI_ASSERT(cpu_fault_ip,
                   offsetof(d2e_x86_cpu, fault_ip) ==
                       D2E_ASM_CPU_FAULT_IP_OFFSET);
D2E_ASM_ABI_ASSERT(cpu_instructions_retired,
                   offsetof(d2e_x86_cpu, instructions_retired) ==
                       D2E_ASM_CPU_INSTRUCTIONS_RETIRED_OFFSET);
D2E_ASM_ABI_ASSERT(program_image,
                   offsetof(d2e_native_program, image) == 20);
D2E_ASM_ABI_ASSERT(program_region,
                   offsetof(d2e_native_program, region) == 44);
D2E_ASM_ABI_ASSERT(program_size, sizeof(d2e_native_program) == 48);
#undef D2E_ASM_ABI_ASSERT
#endif

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

    if (program->format != D2E_NATIVE_IMAGE_COM ||
        program->image_size > UINT16_C(0xff00) ||
        psp + UINT16_C(0x0100) > cpu->memory_size ||
        image + program->image_size > cpu->memory_size) {
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
    return cpu->stop_reason == D2E_X86_RUNNING;
}

int d2e_native_load_mz(d2e_x86_cpu *cpu,
                       const d2e_native_program *program) {
    uint16_t psp_segment;
    uint32_t psp;
    uint32_t image;
    size_t index;

    if (program->format != D2E_NATIVE_IMAGE_MZ ||
        program->load_segment < UINT16_C(0x0010) ||
        (program->relocation_count != 0U && program->relocations == NULL)) {
        return 0;
    }
    psp_segment = (uint16_t)(program->load_segment - UINT16_C(0x0010));
    psp = d2e_x86_linear(psp_segment, 0);
    image = d2e_x86_linear(program->load_segment, 0);
    if (psp + UINT16_C(0x0100) > cpu->memory_size ||
        image + program->image_size > cpu->memory_size) {
        return 0;
    }
    for (index = 0; index < program->relocation_count; ++index) {
        const d2e_mz_relocation *const relocation =
            &program->relocations[index];
        const uint32_t module_offset =
            (uint32_t)relocation->segment * UINT32_C(16) +
            relocation->offset;
        if (module_offset + 1U >= program->image_size) {
            return 0;
        }
    }

    d2e_x86_cpu_reset(cpu);
    memset(cpu->memory + psp, 0, UINT16_C(0x0100));
    memcpy(cpu->memory + image, program->image, program->image_size);
    cpu->memory[psp] = UINT8_C(0xcd);
    cpu->memory[psp + 1U] = UINT8_C(0x20);

    for (index = 0; index < program->relocation_count; ++index) {
        const d2e_mz_relocation *const relocation =
            &program->relocations[index];
        const uint32_t module_offset =
            (uint32_t)relocation->segment * UINT32_C(16) +
            relocation->offset;
        const uint32_t address = image + module_offset;
        uint16_t value;
        value = (uint16_t)(cpu->memory[address] |
                           ((uint16_t)cpu->memory[address + 1U] << 8U));
        value = (uint16_t)(value + program->load_segment);
        cpu->memory[address] = (uint8_t)value;
        cpu->memory[address + 1U] = (uint8_t)(value >> 8U);
    }

    cpu->segments[D2E_X86_CS] =
        (uint16_t)(program->load_segment + program->entry_cs);
    cpu->segments[D2E_X86_SS] =
        (uint16_t)(program->load_segment + program->initial_ss);
    cpu->segments[D2E_X86_DS] = psp_segment;
    cpu->segments[D2E_X86_ES] = psp_segment;
    cpu->regs[D2E_X86_SP] = program->initial_sp;
    cpu->ip = program->entry_ip;
    return cpu->stop_reason == D2E_X86_RUNNING;
}

int d2e_native_load(d2e_x86_cpu *cpu,
                    const d2e_native_program *program) {
    if (program == NULL) {
        return 0;
    }
    switch (program->format) {
        case D2E_NATIVE_IMAGE_COM:
            return d2e_native_load_com(cpu, program);
        case D2E_NATIVE_IMAGE_MZ:
            return d2e_native_load_mz(cpu, program);
        default:
            return 0;
    }
}

d2e_x86_stop_reason d2e_native_run(d2e_x86_cpu *cpu,
                                   const d2e_native_program *program,
                                   uint32_t block_budget) {
    uint32_t block_count = 0;
    cpu->stop_reason = D2E_X86_RUNNING;
    if (program->region != NULL) {
        (void)program->region(cpu, block_budget);
        if (cpu->stop_reason == D2E_X86_RUNNING) {
            cpu->stop_reason = D2E_X86_BUDGET_EXHAUSTED;
        }
        return cpu->stop_reason;
    }
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
    if (cpu->interrupt != NULL &&
        cpu->interrupt(cpu->interrupt_context, cpu, interrupt_number)) {
        return;
    }
    cpu->fault_cs = cpu->segments[D2E_X86_CS];
    cpu->fault_ip = cpu->ip;
    cpu->fault_address =
        ((uint32_t)interrupt_number << 8U) | d2e_x86_get_reg8(cpu, 4U);
    cpu->stop_reason = D2E_X86_UNHANDLED_INTERRUPT;
}
