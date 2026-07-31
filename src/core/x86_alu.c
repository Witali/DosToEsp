#include "d2e/x86_alu.h"

static uint16_t parity_flag(uint8_t value) {
    value ^= (uint8_t)(value >> 4U);
    value &= UINT8_C(0x0f);
    return (UINT16_C(0x9669) >> value) & 1U ? D2E_X86_FLAG_PF : 0U;
}

static uint16_t common_flags8(uint8_t result) {
    uint16_t flags = parity_flag(result);
    if (result == 0U) {
        flags |= D2E_X86_FLAG_ZF;
    }
    if ((result & UINT8_C(0x80)) != 0U) {
        flags |= D2E_X86_FLAG_SF;
    }
    return flags;
}

static uint16_t common_flags16(uint16_t result) {
    uint16_t flags = parity_flag((uint8_t)result);
    if (result == 0U) {
        flags |= D2E_X86_FLAG_ZF;
    }
    if ((result & UINT16_C(0x8000)) != 0U) {
        flags |= D2E_X86_FLAG_SF;
    }
    return flags;
}

static void replace_arithmetic_flags(d2e_x86_cpu *cpu, uint16_t flags) {
    const uint16_t mask = D2E_X86_FLAG_CF | D2E_X86_FLAG_PF |
                          D2E_X86_FLAG_AF | D2E_X86_FLAG_ZF |
                          D2E_X86_FLAG_SF | D2E_X86_FLAG_OF;
    cpu->flags = (uint16_t)((cpu->flags & (uint16_t)~mask) | flags |
                            D2E_X86_FLAG_FIXED);
}

uint8_t d2e_x86_add8(d2e_x86_cpu *cpu, uint8_t left, uint8_t right) {
    const uint16_t wide = (uint16_t)left + (uint16_t)right;
    const uint8_t result = (uint8_t)wide;
    uint16_t flags = common_flags8(result);
    if (wide > UINT8_MAX) {
        flags |= D2E_X86_FLAG_CF;
    }
    if (((left ^ right ^ result) & UINT8_C(0x10)) != 0U) {
        flags |= D2E_X86_FLAG_AF;
    }
    if (((uint8_t)~(left ^ right) & (left ^ result) & UINT8_C(0x80)) != 0U) {
        flags |= D2E_X86_FLAG_OF;
    }
    replace_arithmetic_flags(cpu, flags);
    return result;
}

uint16_t d2e_x86_add16(d2e_x86_cpu *cpu, uint16_t left, uint16_t right) {
    const uint32_t wide = (uint32_t)left + (uint32_t)right;
    const uint16_t result = (uint16_t)wide;
    uint16_t flags = common_flags16(result);
    if (wide > UINT16_MAX) {
        flags |= D2E_X86_FLAG_CF;
    }
    if (((left ^ right ^ result) & UINT16_C(0x10)) != 0U) {
        flags |= D2E_X86_FLAG_AF;
    }
    if (((uint16_t)~(left ^ right) & (left ^ result) &
         UINT16_C(0x8000)) != 0U) {
        flags |= D2E_X86_FLAG_OF;
    }
    replace_arithmetic_flags(cpu, flags);
    return result;
}

uint8_t d2e_x86_sub8(d2e_x86_cpu *cpu, uint8_t left, uint8_t right) {
    const uint8_t result = (uint8_t)(left - right);
    uint16_t flags = common_flags8(result);
    if (left < right) {
        flags |= D2E_X86_FLAG_CF;
    }
    if (((left ^ right ^ result) & UINT8_C(0x10)) != 0U) {
        flags |= D2E_X86_FLAG_AF;
    }
    if (((left ^ right) & (left ^ result) & UINT8_C(0x80)) != 0U) {
        flags |= D2E_X86_FLAG_OF;
    }
    replace_arithmetic_flags(cpu, flags);
    return result;
}

uint16_t d2e_x86_sub16(d2e_x86_cpu *cpu, uint16_t left, uint16_t right) {
    const uint16_t result = (uint16_t)(left - right);
    uint16_t flags = common_flags16(result);
    if (left < right) {
        flags |= D2E_X86_FLAG_CF;
    }
    if (((left ^ right ^ result) & UINT16_C(0x10)) != 0U) {
        flags |= D2E_X86_FLAG_AF;
    }
    if (((left ^ right) & (left ^ result) & UINT16_C(0x8000)) != 0U) {
        flags |= D2E_X86_FLAG_OF;
    }
    replace_arithmetic_flags(cpu, flags);
    return result;
}

uint8_t d2e_x86_inc8(d2e_x86_cpu *cpu, uint8_t value) {
    const uint16_t carry = cpu->flags & D2E_X86_FLAG_CF;
    const uint8_t result = d2e_x86_add8(cpu, value, 1U);
    cpu->flags = (uint16_t)((cpu->flags & (uint16_t)~D2E_X86_FLAG_CF) | carry);
    return result;
}

uint16_t d2e_x86_inc16(d2e_x86_cpu *cpu, uint16_t value) {
    const uint16_t carry = cpu->flags & D2E_X86_FLAG_CF;
    const uint16_t result = d2e_x86_add16(cpu, value, 1U);
    cpu->flags = (uint16_t)((cpu->flags & (uint16_t)~D2E_X86_FLAG_CF) | carry);
    return result;
}

uint8_t d2e_x86_dec8(d2e_x86_cpu *cpu, uint8_t value) {
    const uint16_t carry = cpu->flags & D2E_X86_FLAG_CF;
    const uint8_t result = d2e_x86_sub8(cpu, value, 1U);
    cpu->flags = (uint16_t)((cpu->flags & (uint16_t)~D2E_X86_FLAG_CF) | carry);
    return result;
}

uint16_t d2e_x86_dec16(d2e_x86_cpu *cpu, uint16_t value) {
    const uint16_t carry = cpu->flags & D2E_X86_FLAG_CF;
    const uint16_t result = d2e_x86_sub16(cpu, value, 1U);
    cpu->flags = (uint16_t)((cpu->flags & (uint16_t)~D2E_X86_FLAG_CF) | carry);
    return result;
}

uint8_t d2e_x86_logic8(d2e_x86_cpu *cpu, uint8_t value) {
    replace_arithmetic_flags(cpu, common_flags8(value));
    return value;
}

uint16_t d2e_x86_logic16(d2e_x86_cpu *cpu, uint16_t value) {
    replace_arithmetic_flags(cpu, common_flags16(value));
    return value;
}

