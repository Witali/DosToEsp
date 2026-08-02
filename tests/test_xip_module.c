#include "d2e/xip_module.h"

#include <stdio.h>
#include <string.h>

static unsigned failures;
static uint8_t module[UINT32_C(0x20200)];

#define CHECK(expression)                                                       \
    do {                                                                        \
        if (!(expression)) {                                                    \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__,  \
                    #expression);                                               \
            ++failures;                                                         \
        }                                                                       \
    } while (0)

static void write_u16(size_t offset, uint16_t value) {
    module[offset] = (uint8_t)value;
    module[offset + 1U] = (uint8_t)(value >> 8U);
}

static void write_u32(size_t offset, uint32_t value) {
    module[offset] = (uint8_t)value;
    module[offset + 1U] = (uint8_t)(value >> 8U);
    module[offset + 2U] = (uint8_t)(value >> 16U);
    module[offset + 3U] = (uint8_t)(value >> 24U);
}

static void make_module(void) {
    memset(module, 0, sizeof(module));
    memcpy(module, "D2EXIP1", 7U);
    write_u32(8U, D2E_XIP_FORMAT_VERSION);
    write_u32(12U, D2E_XIP_HEADER_SIZE);
    write_u32(16U, D2E_PACKAGE_ABI_VERSION);
    write_u32(20U, D2E_XIP_SHELL_ABI_VERSION);
    write_u32(28U, sizeof(module));
    write_u32(32U, UINT32_C(0x10000));
    write_u32(36U, UINT32_C(0x100));
    write_u32(40U, UINT32_C(0x20000));
    write_u32(44U, UINT32_C(0x200));
    write_u32(48U, D2E_XIP_HEADER_SIZE);
    write_u32(52U, 1U);
    write_u32(56U, UINT32_C(0x20));
    write_u32(60U, UINT32_C(0x1000));
    write_u32(64U, D2E_XIP_HEADER_SIZE + D2E_XIP_RELOCATION_SIZE);
    write_u32(68U, 1U);
    write_u32(72U, D2E_XIP_HEADER_SIZE + D2E_XIP_RELOCATION_SIZE +
                         D2E_XIP_FRAGMENT_SIZE);
    write_u32(76U, 1U);
    write_u32(80U, D2E_NATIVE_IMAGE_MZ);
    write_u16(84U, UINT16_C(0x1000));
    write_u16(86U, UINT16_C(0x0010));
    write_u16(88U, UINT16_C(0x0020));
    write_u16(90U, UINT16_C(0x0030));
    write_u16(92U, UINT16_C(0xfffe));
    memcpy(module + 100U, "ALLEY", 6U);
    memcpy(module + 109U, "alley_cat", 10U);
    memcpy(module + 141U, "Alley Cat", 10U);

    write_u32(D2E_XIP_HEADER_SIZE, UINT32_C(0x10040));
    write_u32(D2E_XIP_HEADER_SIZE + 4U, D2E_XIP_TARGET_DROM);
    write_u32(D2E_XIP_HEADER_SIZE + 8U, UINT32_C(0x80));
    write_u32(D2E_XIP_HEADER_SIZE + 12U, UINT32_C(4));

    write_u32(D2E_XIP_HEADER_SIZE + D2E_XIP_RELOCATION_SIZE, 0U);
    write_u32(D2E_XIP_HEADER_SIZE + D2E_XIP_RELOCATION_SIZE + 4U,
              UINT32_C(0x20080));
    write_u32(D2E_XIP_HEADER_SIZE + D2E_XIP_RELOCATION_SIZE + 8U, 4U);
    write_u16(D2E_XIP_HEADER_SIZE + D2E_XIP_RELOCATION_SIZE +
                  D2E_XIP_FRAGMENT_SIZE,
              UINT16_C(0x0042));
    write_u16(D2E_XIP_HEADER_SIZE + D2E_XIP_RELOCATION_SIZE +
                  D2E_XIP_FRAGMENT_SIZE + 2U,
              UINT16_C(0x0010));
}

static void test_valid_module(void) {
    d2e_xip_module_view view;
    d2e_xip_relocation relocation;
    d2e_xip_fragment fragment;
    d2e_mz_relocation mz;
    make_module();
    CHECK(d2e_xip_module_open(&view, module, sizeof(module)));
    CHECK(strcmp(view.manifest.command, "ALLEY") == 0);
    CHECK(view.manifest.region_offset == UINT32_C(0x20));
    CHECK(d2e_xip_relocation_at(&view, 0U, &relocation));
    CHECK(relocation.patch_offset == UINT32_C(0x10040));
    CHECK(relocation.target_kind == D2E_XIP_TARGET_DROM);
    CHECK(relocation.target == UINT32_C(0x80));
    CHECK(relocation.addend == 4);
    CHECK(d2e_xip_fragment_at(&view, 0U, &fragment));
    CHECK(fragment.data_offset == UINT32_C(0x20080));
    CHECK(d2e_xip_mz_relocation_at(&view, 0U, &mz));
    CHECK(mz.offset == UINT16_C(0x0042));
    CHECK(mz.segment == UINT16_C(0x0010));
    CHECK(!d2e_xip_relocation_at(&view, 1U, &relocation));
}

static void test_rejections(void) {
    d2e_xip_module_view view;
    make_module();
    module[0] = 'X';
    CHECK(!d2e_xip_module_open(&view, module, sizeof(module)));
    make_module();
    write_u32(32U, UINT32_C(0x10001));
    CHECK(!d2e_xip_module_open(&view, module, sizeof(module)));
    make_module();
    write_u32(28U, UINT32_MAX);
    CHECK(!d2e_xip_module_open(&view, module, sizeof(module)));
    make_module();
    write_u32(D2E_XIP_HEADER_SIZE, UINT32_C(0x10041));
    CHECK(!d2e_xip_module_open(&view, module, sizeof(module)));
    make_module();
    write_u32(D2E_XIP_HEADER_SIZE + D2E_XIP_RELOCATION_SIZE + 4U,
              UINT32_C(0x10080));
    CHECK(!d2e_xip_module_open(&view, module, sizeof(module)));
    make_module();
    memset(module + 100U, 'X', D2E_XIP_COMMAND_SIZE);
    CHECK(!d2e_xip_module_open(&view, module, sizeof(module)));
}

int main(void) {
    test_valid_module();
    test_rejections();
    if (failures != 0U) {
        fprintf(stderr, "%u XIP module test(s) failed\n", failures);
        return 1;
    }
    puts("D2E XIP module format tests passed");
    return 0;
}
