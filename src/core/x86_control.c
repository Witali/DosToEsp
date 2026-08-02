#include "d2e/x86_control.h"

enum {
    D2E_X86_POPF_MASK = 0x0fd5U
};

static uint16_t push16(d2e_x86_cpu *cpu, uint16_t stack_pointer,
                       uint16_t value) {
    stack_pointer = (uint16_t)(stack_pointer - UINT16_C(2));
    d2e_x86_write16_seg(cpu, cpu->segments[D2E_X86_SS], stack_pointer,
                        value);
    return stack_pointer;
}

uint16_t d2e_x86_push_flags(d2e_x86_cpu *cpu, uint16_t stack_pointer) {
    return push16(cpu, stack_pointer,
                  (uint16_t)(cpu->flags | D2E_X86_FLAG_FIXED));
}

uint16_t d2e_x86_pop_flags(d2e_x86_cpu *cpu, uint16_t stack_pointer) {
    const uint16_t value = d2e_x86_read16_seg(
        cpu, cpu->segments[D2E_X86_SS], stack_pointer);
    cpu->flags = (uint16_t)((value & D2E_X86_POPF_MASK) |
                            D2E_X86_FLAG_FIXED);
    return (uint16_t)(stack_pointer + UINT16_C(2));
}

uint16_t d2e_x86_push_near_return(d2e_x86_cpu *cpu,
                                  uint16_t stack_pointer,
                                  uint16_t return_ip) {
    return push16(cpu, stack_pointer, return_ip);
}

uint16_t d2e_x86_push_far_return(d2e_x86_cpu *cpu,
                                 uint16_t stack_pointer,
                                 uint16_t return_cs,
                                 uint16_t return_ip) {
    stack_pointer = push16(cpu, stack_pointer, return_cs);
    return push16(cpu, stack_pointer, return_ip);
}

uint16_t d2e_x86_call_near(d2e_x86_cpu *cpu, uint16_t stack_pointer,
                           uint16_t return_ip, uint16_t target_ip) {
    stack_pointer = d2e_x86_push_near_return(cpu, stack_pointer, return_ip);
    cpu->ip = target_ip;
    return stack_pointer;
}

uint16_t d2e_x86_call_far(d2e_x86_cpu *cpu, uint16_t stack_pointer,
                          uint16_t return_ip, uint16_t target_cs,
                          uint16_t target_ip) {
    stack_pointer = d2e_x86_push_far_return(
        cpu, stack_pointer, cpu->segments[D2E_X86_CS], return_ip);
    cpu->segments[D2E_X86_CS] = target_cs;
    cpu->ip = target_ip;
    return stack_pointer;
}

uint16_t d2e_x86_return_near(d2e_x86_cpu *cpu, uint16_t stack_pointer,
                             uint16_t cleanup) {
    cpu->ip = d2e_x86_read16_seg(
        cpu, cpu->segments[D2E_X86_SS], stack_pointer);
    return (uint16_t)(stack_pointer + UINT16_C(2) + cleanup);
}

uint16_t d2e_x86_return_far(d2e_x86_cpu *cpu, uint16_t stack_pointer,
                            uint16_t cleanup) {
    cpu->ip = d2e_x86_read16_seg(
        cpu, cpu->segments[D2E_X86_SS], stack_pointer);
    cpu->segments[D2E_X86_CS] = d2e_x86_read16_seg(
        cpu, cpu->segments[D2E_X86_SS],
        (uint16_t)(stack_pointer + UINT16_C(2)));
    return (uint16_t)(stack_pointer + UINT16_C(4) + cleanup);
}

uint16_t d2e_x86_iret(d2e_x86_cpu *cpu, uint16_t stack_pointer) {
    cpu->ip = d2e_x86_read16_seg(
        cpu, cpu->segments[D2E_X86_SS], stack_pointer);
    cpu->segments[D2E_X86_CS] = d2e_x86_read16_seg(
        cpu, cpu->segments[D2E_X86_SS],
        (uint16_t)(stack_pointer + UINT16_C(2)));
    cpu->flags = (uint16_t)((d2e_x86_read16_seg(
                                cpu, cpu->segments[D2E_X86_SS],
                                (uint16_t)(stack_pointer + UINT16_C(4))) &
                            D2E_X86_POPF_MASK) |
                            D2E_X86_FLAG_FIXED);
    return (uint16_t)(stack_pointer + UINT16_C(6));
}
