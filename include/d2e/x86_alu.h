#ifndef D2E_X86_ALU_H
#define D2E_X86_ALU_H

#include "d2e/x86_cpu.h"

#ifdef __cplusplus
extern "C" {
#endif

uint8_t d2e_x86_add8(d2e_x86_cpu *cpu, uint8_t left, uint8_t right);
uint16_t d2e_x86_add16(d2e_x86_cpu *cpu, uint16_t left, uint16_t right);
uint8_t d2e_x86_sub8(d2e_x86_cpu *cpu, uint8_t left, uint8_t right);
uint16_t d2e_x86_sub16(d2e_x86_cpu *cpu, uint16_t left, uint16_t right);
uint8_t d2e_x86_inc8(d2e_x86_cpu *cpu, uint8_t value);
uint16_t d2e_x86_inc16(d2e_x86_cpu *cpu, uint16_t value);
uint8_t d2e_x86_dec8(d2e_x86_cpu *cpu, uint8_t value);
uint16_t d2e_x86_dec16(d2e_x86_cpu *cpu, uint16_t value);
uint8_t d2e_x86_logic8(d2e_x86_cpu *cpu, uint8_t value);
uint16_t d2e_x86_logic16(d2e_x86_cpu *cpu, uint16_t value);

#ifdef __cplusplus
}
#endif

#endif

