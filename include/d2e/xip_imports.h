#ifndef D2E_XIP_IMPORTS_H
#define D2E_XIP_IMPORTS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define D2E_XIP_IMPORT_LIST(X)                                                  \
    X(0, D2E_XIP_IMPORT_NATIVE_HELPER_PUSH_NEAR_RETURN,                         \
      d2e_native_helper_push_near_return)                                       \
    X(1, D2E_XIP_IMPORT_NATIVE_HELPER_READ16, d2e_native_helper_read16)         \
    X(2, D2E_XIP_IMPORT_NATIVE_HELPER_READ8, d2e_native_helper_read8)           \
    X(3, D2E_XIP_IMPORT_NATIVE_HELPER_WRITE16, d2e_native_helper_write16)       \
    X(4, D2E_XIP_IMPORT_NATIVE_HELPER_WRITE8, d2e_native_helper_write8)         \
    X(5, D2E_XIP_IMPORT_NATIVE_INTERRUPT, d2e_native_interrupt)                 \
    X(6, D2E_XIP_IMPORT_PATTERN_COPY16, d2e_pattern_copy16)                    \
    X(7, D2E_XIP_IMPORT_PATTERN_COPY8, d2e_pattern_copy8)                      \
    X(8, D2E_XIP_IMPORT_PATTERN_FILL16, d2e_pattern_fill16)                    \
    X(9, D2E_XIP_IMPORT_PATTERN_FILL8, d2e_pattern_fill8)                      \
    X(10, D2E_XIP_IMPORT_X86_AAA, d2e_x86_aaa)                                 \
    X(11, D2E_XIP_IMPORT_X86_ADC8, d2e_x86_adc8)                               \
    X(12, D2E_XIP_IMPORT_X86_ADD16, d2e_x86_add16)                             \
    X(13, D2E_XIP_IMPORT_X86_ADD8, d2e_x86_add8)                               \
    X(14, D2E_XIP_IMPORT_X86_DEC16, d2e_x86_dec16)                             \
    X(15, D2E_XIP_IMPORT_X86_DEC8, d2e_x86_dec8)                               \
    X(16, D2E_XIP_IMPORT_X86_INC16, d2e_x86_inc16)                             \
    X(17, D2E_XIP_IMPORT_X86_INC8, d2e_x86_inc8)                               \
    X(18, D2E_XIP_IMPORT_X86_IRET, d2e_x86_iret)                               \
    X(19, D2E_XIP_IMPORT_X86_LINEAR, d2e_x86_linear)                           \
    X(20, D2E_XIP_IMPORT_X86_LOGIC16, d2e_x86_logic16)                         \
    X(21, D2E_XIP_IMPORT_X86_LOGIC8, d2e_x86_logic8)                           \
    X(22, D2E_XIP_IMPORT_X86_MUL8, d2e_x86_mul8)                               \
    X(23, D2E_XIP_IMPORT_X86_POP_FLAGS, d2e_x86_pop_flags)                     \
    X(24, D2E_XIP_IMPORT_X86_POP16, d2e_x86_pop16)                             \
    X(25, D2E_XIP_IMPORT_X86_PORT_IN8, d2e_x86_port_in8)                       \
    X(26, D2E_XIP_IMPORT_X86_PORT_OUT8, d2e_x86_port_out8)                     \
    X(27, D2E_XIP_IMPORT_X86_PUSH_FLAGS, d2e_x86_push_flags)                   \
    X(28, D2E_XIP_IMPORT_X86_PUSH_NEAR_RETURN,                                 \
      d2e_x86_push_near_return)                                                \
    X(29, D2E_XIP_IMPORT_X86_PUSH16, d2e_x86_push16)                           \
    X(30, D2E_XIP_IMPORT_X86_RCL8, d2e_x86_rcl8)                               \
    X(31, D2E_XIP_IMPORT_X86_RCR16, d2e_x86_rcr16)                             \
    X(32, D2E_XIP_IMPORT_X86_RCR8, d2e_x86_rcr8)                               \
    X(33, D2E_XIP_IMPORT_X86_READ16_SEG, d2e_x86_read16_seg)                   \
    X(34, D2E_XIP_IMPORT_X86_READ8, d2e_x86_read8)                             \
    X(35, D2E_XIP_IMPORT_X86_RETURN_FAR, d2e_x86_return_far)                   \
    X(36, D2E_XIP_IMPORT_X86_RETURN_NEAR, d2e_x86_return_near)                 \
    X(37, D2E_XIP_IMPORT_X86_SHL16, d2e_x86_shl16)                             \
    X(38, D2E_XIP_IMPORT_X86_SHL8, d2e_x86_shl8)                               \
    X(39, D2E_XIP_IMPORT_X86_SHR16, d2e_x86_shr16)                             \
    X(40, D2E_XIP_IMPORT_X86_SHR8, d2e_x86_shr8)                               \
    X(41, D2E_XIP_IMPORT_X86_SUB16, d2e_x86_sub16)                             \
    X(42, D2E_XIP_IMPORT_X86_SUB8, d2e_x86_sub8)                               \
    X(43, D2E_XIP_IMPORT_X86_WRITE16_SEG, d2e_x86_write16_seg)                 \
    X(44, D2E_XIP_IMPORT_X86_WRITE8, d2e_x86_write8)                           \
    X(45, D2E_XIP_IMPORT_X86_PORT_IN16, d2e_x86_port_in16)                     \
    X(46, D2E_XIP_IMPORT_X86_PORT_OUT16, d2e_x86_port_out16)

typedef enum d2e_xip_import {
#define D2E_XIP_ENUM_IMPORT(index, name, symbol) name = index,
    D2E_XIP_IMPORT_LIST(D2E_XIP_ENUM_IMPORT)
#undef D2E_XIP_ENUM_IMPORT
    D2E_XIP_IMPORT_COUNT = 47
} d2e_xip_import;

int d2e_xip_import_resolve(uint32_t index, uintptr_t *address);
uint32_t d2e_xip_import_fingerprint(void);

#ifdef __cplusplus
}
#endif

#endif
