#include "d2e/xip_imports.h"

#include "d2e/native_helpers.h"
#include "d2e/native_patterns.h"
#include "d2e/native_runtime.h"
#include "d2e/x86_alu.h"
#include "d2e/x86_control.h"
#include "d2e/x86_cpu.h"

int d2e_xip_import_resolve(uint32_t index, uintptr_t *address) {
    if (address == NULL) {
        return 0;
    }
    switch (index) {
#define D2E_XIP_RESOLVE_IMPORT(number, name, symbol)                             \
    case name:                                                                  \
        *address = (uintptr_t)symbol;                                            \
        return 1;
        D2E_XIP_IMPORT_LIST(D2E_XIP_RESOLVE_IMPORT)
#undef D2E_XIP_RESOLVE_IMPORT
    default:
        *address = 0U;
        return 0;
    }
}

uint32_t d2e_xip_import_fingerprint(void) {
    uint32_t hash = UINT32_C(2166136261);
    uint32_t index;
    for (index = 0U; index < D2E_XIP_IMPORT_COUNT; ++index) {
        uintptr_t address;
        unsigned byte;
        (void)d2e_xip_import_resolve(index, &address);
        for (byte = 0U; byte < sizeof(address); ++byte) {
            hash = (hash ^ (uint8_t)(address >> (byte * 8U))) *
                   UINT32_C(16777619);
        }
    }
    return hash;
}
