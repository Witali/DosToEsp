set(d2e_root "${CMAKE_CURRENT_LIST_DIR}/../../..")
option(D2E_QEMU_SMOKE "Restart after the native smoke test" OFF)

idf_component_register(
    SRCS
        "main.c"
        "generated/native_smoke.c"
        "${d2e_root}/src/core/native_runtime.c"
        "${d2e_root}/src/core/x86_alu.c"
        "${d2e_root}/src/core/x86_cpu.c"
        "${d2e_root}/src/core/x86_memory.c"
        "${d2e_root}/src/devices/cga.c"
    INCLUDE_DIRS
        "."
        "${d2e_root}/include"
    REQUIRES
        esp_system
        freertos
        heap
)

target_compile_options(${COMPONENT_LIB} PRIVATE -O3 -Wall -Wextra -Werror)
if(D2E_QEMU_SMOKE)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE D2E_QEMU_SMOKE=1)
endif()
