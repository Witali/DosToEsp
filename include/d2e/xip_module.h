#ifndef D2E_XIP_MODULE_H
#define D2E_XIP_MODULE_H

#include "d2e/package.h"

#ifdef __cplusplus
extern "C" {
#endif

#define D2E_XIP_FORMAT_VERSION UINT32_C(1)
#define D2E_XIP_SHELL_ABI_VERSION UINT32_C(1)
#define D2E_XIP_HEADER_SIZE UINT32_C(256)
#define D2E_XIP_FLASH_PAGE_SIZE UINT32_C(0x10000)
#define D2E_XIP_RELOCATION_SIZE UINT32_C(16)
#define D2E_XIP_FRAGMENT_SIZE UINT32_C(12)
#define D2E_XIP_MZ_RELOCATION_SIZE UINT32_C(4)
#define D2E_XIP_COMMAND_SIZE 9U
#define D2E_XIP_NAME_SIZE 32U
#define D2E_XIP_TITLE_SIZE 64U
#define D2E_XIP_HASH_SIZE 32U

typedef enum d2e_xip_target_kind {
    D2E_XIP_TARGET_IROM = 0,
    D2E_XIP_TARGET_DROM = 1,
    D2E_XIP_TARGET_IMPORT = 2
} d2e_xip_target_kind;

typedef struct d2e_xip_manifest {
    uint32_t flags;
    uint32_t module_size;
    uint32_t irom_offset;
    uint32_t irom_size;
    uint32_t drom_offset;
    uint32_t drom_size;
    uint32_t relocation_offset;
    uint32_t relocation_count;
    uint32_t region_offset;
    uint32_t image_size;
    uint32_t fragment_offset;
    uint32_t fragment_count;
    uint32_t mz_relocation_offset;
    uint32_t mz_relocation_count;
    d2e_native_image_format image_format;
    uint16_t load_segment;
    uint16_t entry_cs;
    uint16_t entry_ip;
    uint16_t initial_ss;
    uint16_t initial_sp;
    char command[D2E_XIP_COMMAND_SIZE];
    char name[D2E_XIP_NAME_SIZE];
    char title[D2E_XIP_TITLE_SIZE];
    uint8_t sha256[D2E_XIP_HASH_SIZE];
} d2e_xip_manifest;

typedef struct d2e_xip_relocation {
    uint32_t patch_offset;
    d2e_xip_target_kind target_kind;
    uint32_t target;
    int32_t addend;
} d2e_xip_relocation;

typedef struct d2e_xip_fragment {
    uint32_t image_offset;
    uint32_t data_offset;
    uint32_t size;
} d2e_xip_fragment;

typedef struct d2e_xip_module_view {
    const uint8_t *bytes;
    size_t byte_count;
    d2e_xip_manifest manifest;
} d2e_xip_module_view;

int d2e_xip_module_open(d2e_xip_module_view *view, const void *bytes,
                        size_t byte_count);
int d2e_xip_relocation_at(const d2e_xip_module_view *view, size_t index,
                          d2e_xip_relocation *relocation);
int d2e_xip_fragment_at(const d2e_xip_module_view *view, size_t index,
                        d2e_xip_fragment *fragment);
int d2e_xip_mz_relocation_at(const d2e_xip_module_view *view, size_t index,
                             d2e_mz_relocation *relocation);

#ifdef __cplusplus
}
#endif

#endif
