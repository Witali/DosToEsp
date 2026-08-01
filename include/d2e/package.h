#ifndef D2E_PACKAGE_H
#define D2E_PACKAGE_H

#include "d2e/native_runtime.h"

#ifdef __cplusplus
extern "C" {
#endif

#define D2E_PACKAGE_ABI_VERSION UINT32_C(1)
#define D2E_PACKAGE_COMMAND_MAX 8U

typedef enum d2e_package_storage {
    D2E_PACKAGE_BUILTIN_FLASH = 0,
    D2E_PACKAGE_EXTERNAL_MODULE = 1
} d2e_package_storage;

typedef struct d2e_package {
    uint32_t abi_version;
    const char *command;
    const char *title;
    d2e_package_storage storage;
    const d2e_native_program *program;
} d2e_package;

int d2e_package_validate(const d2e_package *package);
const d2e_package *d2e_package_find(const d2e_package *packages,
                                    size_t package_count,
                                    const char *command);

#ifdef __cplusplus
}
#endif

#endif
