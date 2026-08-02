#ifndef D2E_X86_CONTROL_H
#define D2E_X86_CONTROL_H

#include "d2e/x86_cpu.h"

#ifdef __cplusplus
extern "C" {
#endif

uint16_t d2e_x86_push_flags(d2e_x86_cpu *cpu, uint16_t stack_pointer);
uint16_t d2e_x86_pop_flags(d2e_x86_cpu *cpu, uint16_t stack_pointer);

uint16_t d2e_x86_push_near_return(d2e_x86_cpu *cpu,
                                  uint16_t stack_pointer,
                                  uint16_t return_ip);
uint16_t d2e_x86_push_far_return(d2e_x86_cpu *cpu,
                                 uint16_t stack_pointer,
                                 uint16_t return_cs,
                                 uint16_t return_ip);
uint16_t d2e_x86_call_near(d2e_x86_cpu *cpu, uint16_t stack_pointer,
                           uint16_t return_ip, uint16_t target_ip);
uint16_t d2e_x86_call_far(d2e_x86_cpu *cpu, uint16_t stack_pointer,
                          uint16_t return_ip, uint16_t target_cs,
                          uint16_t target_ip);
uint16_t d2e_x86_return_near(d2e_x86_cpu *cpu, uint16_t stack_pointer,
                             uint16_t cleanup);
uint16_t d2e_x86_return_far(d2e_x86_cpu *cpu, uint16_t stack_pointer,
                            uint16_t cleanup);
uint16_t d2e_x86_iret(d2e_x86_cpu *cpu, uint16_t stack_pointer);

#ifdef __cplusplus
}
#endif

#endif
