#ifndef D2E_NATIVE_ASM_OFFSETS_H
#define D2E_NATIVE_ASM_OFFSETS_H

/*
 * Stable 32-bit ABI offsets used by generated Xtensa assembly. Keep the
 * matching compile-time checks in native_runtime.c in sync with this file.
 */
#define D2E_ASM_CPU_REGS_OFFSET 0
#define D2E_ASM_CPU_SEGMENTS_OFFSET 16
#define D2E_ASM_CPU_IP_OFFSET 24
#define D2E_ASM_CPU_FLAGS_OFFSET 26
#define D2E_ASM_CPU_STOP_REASON_OFFSET 72
#define D2E_ASM_CPU_FAULT_CS_OFFSET 76
#define D2E_ASM_CPU_FAULT_IP_OFFSET 78
#define D2E_ASM_CPU_INSTRUCTIONS_RETIRED_OFFSET 88

#define D2E_ASM_X86_ES_INDEX 0
#define D2E_ASM_X86_CS_INDEX 1
#define D2E_ASM_X86_SS_INDEX 2
#define D2E_ASM_X86_DS_INDEX 3
#define D2E_ASM_X86_FLAG_FIXED 2
#define D2E_ASM_STOP_EXITED 1
#define D2E_ASM_STOP_UNTRANSLATED_TARGET 2

#endif
