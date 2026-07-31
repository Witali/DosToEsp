set(d2e_root "${CMAKE_CURRENT_LIST_DIR}/../../..")
option(D2E_QEMU_SMOKE "Restart after the native smoke test" OFF)
option(D2E_ALLEY_CAT "Build the generated Alley Cat MZ program" OFF)

if(D2E_ALLEY_CAT)
    set(d2e_generated_source "generated/alley-cat/game_native.c")
    set_source_files_properties(
        "${d2e_generated_source}"
        PROPERTIES COMPILE_OPTIONS "-O2;-mtext-section-literals"
    )
else()
    set(d2e_generated_source "generated/native_smoke.c")
endif()

idf_component_register(
    SRCS
        "main.c"
        "cyd_display.c"
        "${d2e_generated_source}"
        "${d2e_root}/src/core/native_runtime.c"
        "${d2e_root}/src/core/x86_alu.c"
        "${d2e_root}/src/core/x86_cpu.c"
        "${d2e_root}/src/core/x86_memory.c"
        "${d2e_root}/src/devices/cga.c"
        "${d2e_root}/src/devices/cp437_font.c"
        "${d2e_root}/src/devices/text_video.c"
        "${d2e_root}/src/machine/pc_at.c"
    INCLUDE_DIRS
        "."
        "${d2e_root}/include"
    REQUIRES
        esp_driver_gpio
        esp_driver_spi
        esp_lcd
        esp_system
        freertos
        heap
)

target_compile_options(${COMPONENT_LIB} PRIVATE -O3 -Wall -Wextra -Werror)
if(D2E_QEMU_SMOKE)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE D2E_QEMU_SMOKE=1)
endif()
if(D2E_ALLEY_CAT)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE D2E_ALLEY_CAT=1)
endif()
