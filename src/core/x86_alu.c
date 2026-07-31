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

static void replace_shift_flags(d2e_x86_cpu *cpu, uint16_t common,
                                uint16_t carry, uint8_t count,
                                uint16_t overflow) {
    uint16_t mask = D2E_X86_FLAG_CF | D2E_X86_FLAG_PF |
                    D2E_X86_FLAG_ZF | D2E_X86_FLAG_SF;
    uint16_t flags = common | carry;
    if (count == 1U) {
        mask |= D2E_X86_FLAG_OF;
        flags |= overflow;
    }
    cpu->flags = (uint16_t)((cpu->flags & (uint16_t)~mask) | flags |
                            D2E_X86_FLAG_FIXED);
}

uint8_t d2e_x86_shl8(d2e_x86_cpu *cpu, uint8_t value, uint8_t count) {
    uint8_t result = value;
    uint16_t carry = 0;
    uint8_t index;
    if (count == 0U) {
        return value;
    }
    for (index = 0; index < count; ++index) {
        carry = (result & UINT8_C(0x80)) != 0U ? D2E_X86_FLAG_CF : 0U;
        result = (uint8_t)(result << 1U);
    }
    replace_shift_flags(
        cpu, common_flags8(result), carry, count,
        ((result & UINT8_C(0x80)) != 0U) != (carry != 0U)
            ? D2E_X86_FLAG_OF
            : 0U);
    return result;
}

uint16_t d2e_x86_shl16(d2e_x86_cpu *cpu, uint16_t value, uint8_t count) {
    uint16_t result = value;
    uint16_t carry = 0;
    uint8_t index;
    if (count == 0U) {
        return value;
    }
    for (index = 0; index < count; ++index) {
        carry = (result & UINT16_C(0x8000)) != 0U ? D2E_X86_FLAG_CF : 0U;
        result = (uint16_t)(result << 1U);
    }
    replace_shift_flags(
        cpu, common_flags16(result), carry, count,
        ((result & UINT16_C(0x8000)) != 0U) != (carry != 0U)
            ? D2E_X86_FLAG_OF
            : 0U);
    return result;
}

uint8_t d2e_x86_shr8(d2e_x86_cpu *cpu, uint8_t value, uint8_t count) {
    uint8_t result = value;
    uint16_t carry = 0;
    uint8_t index;
    if (count == 0U) {
        return value;
    }
    for (index = 0; index < count; ++index) {
        carry = (result & 1U) != 0U ? D2E_X86_FLAG_CF : 0U;
        result = (uint8_t)(result >> 1U);
    }
    replace_shift_flags(cpu, common_flags8(result), carry, count,
                        (value & UINT8_C(0x80)) != 0U
                            ? D2E_X86_FLAG_OF
                            : 0U);
    return result;
}

uint16_t d2e_x86_shr16(d2e_x86_cpu *cpu, uint16_t value, uint8_t count) {
    uint16_t result = value;
    uint16_t carry = 0;
    uint8_t index;
    if (count == 0U) {
        return value;
    }
    for (index = 0; index < count; ++index) {
        carry = (result & 1U) != 0U ? D2E_X86_FLAG_CF : 0U;
        result = (uint16_t)(result >> 1U);
    }
    replace_shift_flags(cpu, common_flags16(result), carry, count,
                        (value & UINT16_C(0x8000)) != 0U
                            ? D2E_X86_FLAG_OF
                            : 0U);
    return result;
}

static uint32_t rotate_carry(d2e_x86_cpu *cpu, uint32_t value,
                             uint8_t count, unsigned width, int right) {
    const uint32_t value_mask = (UINT32_C(1) << width) - 1U;
    uint32_t carry = (cpu->flags & D2E_X86_FLAG_CF) != 0U;
    uint8_t index;
    if (count == 0U) {
        return value & value_mask;
    }
    for (index = 0; index < count; ++index) {
        if (right) {
            const uint32_t next_carry = value & 1U;
            value = (value >> 1U) | (carry << (width - 1U));
            carry = next_carry;
        } else {
            const uint32_t next_carry = (value >> (width - 1U)) & 1U;
            value = ((value << 1U) & value_mask) | carry;
            carry = next_carry;
        }
    }
    cpu->flags = (uint16_t)((cpu->flags & (uint16_t)~D2E_X86_FLAG_CF) |
                            (carry != 0U ? D2E_X86_FLAG_CF : 0U) |
                            D2E_X86_FLAG_FIXED);
    if (count == 1U) {
        uint16_t overflow;
        if (right) {
            overflow = (((value >> (width - 1U)) ^
                         (value >> (width - 2U))) & 1U) != 0U
                           ? D2E_X86_FLAG_OF
                           : 0U;
        } else {
            overflow = (((value >> (width - 1U)) & 1U) != carry)
                           ? D2E_X86_FLAG_OF
                           : 0U;
        }
        cpu->flags = (uint16_t)((cpu->flags & (uint16_t)~D2E_X86_FLAG_OF) |
                                overflow | D2E_X86_FLAG_FIXED);
    }
    return value & value_mask;
}

uint8_t d2e_x86_rcl8(d2e_x86_cpu *cpu, uint8_t value, uint8_t count) {
    return (uint8_t)rotate_carry(cpu, value, count, 8U, 0);
}

uint16_t d2e_x86_rcl16(d2e_x86_cpu *cpu, uint16_t value, uint8_t count) {
    return (uint16_t)rotate_carry(cpu, value, count, 16U, 0);
}

uint8_t d2e_x86_rcr8(d2e_x86_cpu *cpu, uint8_t value, uint8_t count) {
    return (uint8_t)rotate_carry(cpu, value, count, 8U, 1);
}

uint16_t d2e_x86_rcr16(d2e_x86_cpu *cpu, uint16_t value, uint8_t count) {
    return (uint16_t)rotate_carry(cpu, value, count, 16U, 1);
}
