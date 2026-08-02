set(d2e_root "${CMAKE_CURRENT_LIST_DIR}/../../..")
option(D2E_QEMU_SMOKE "Restart after the native smoke test" OFF)
option(D2E_ALLEY_CAT "Build the generated Alley Cat MZ program" OFF)
option(D2E_XTENSA_ASM_SMOKE "Build the generated Xtensa assembly smoke test" OFF)
option(D2E_XIP_SHELL "Build the shell without a statically linked program" OFF)
set(D2E_SHELL_DEFAULT OFF)
if(D2E_ALLEY_CAT AND D2E_XTENSA_ASM_SMOKE)
    message(FATAL_ERROR "D2E_ALLEY_CAT and D2E_XTENSA_ASM_SMOKE are mutually exclusive")
elseif(D2E_ALLEY_CAT)
    set(D2E_SHELL_DEFAULT ON)
endif()
option(D2E_SHELL "Build the resident translated-program shell"
    ${D2E_SHELL_DEFAULT})
option(D2E_SHELL_AUTORUN "Automatically run the first shell package" OFF)
option(D2E_QEMU_INTERACTIVE "Run Alley Cat continuously in QEMU" OFF)
option(D2E_QEMU_DUMP_FRAME "Dump final CGA VRAM through QEMU UART" OFF)
option(D2E_QEMU_SCRIPTED_INPUT "Inject deterministic Alley Cat keys" OFF)
option(D2E_QEMU_EXIT_AFTER_RETURN
    "Restart the ESP32 after a bounded shell session" OFF)
option(D2E_QEMU_BOARD_DEVICES
    "Use the patched QEMU ST7789 and SDSPI board devices" OFF)
set(D2E_QEMU_INTERACTIVE_FRAME_LIMIT "0" CACHE STRING
    "Optional interactive QEMU frame limit; zero runs continuously")
set(D2E_QEMU_XIP_INSTALL_FILE "" CACHE STRING
    "Optional C: module installed before QEMU shell autorun")

set(d2e_entry_source "main.c")
if(D2E_SHELL)
    set(d2e_entry_source "d2e_shell_main.c")
endif()

if(D2E_ALLEY_CAT)
    file(GLOB d2e_generated_sources CONFIGURE_DEPENDS
        "generated/alley-cat/*.c"
        "generated/alley-cat/*.S")
    if(NOT d2e_generated_sources)
        message(FATAL_ERROR "Generate Alley Cat sources before configuring")
    endif()
    set_source_files_properties(
        ${d2e_generated_sources}
        PROPERTIES COMPILE_OPTIONS "-O2;-mtext-section-literals"
    )
elseif(D2E_XTENSA_ASM_SMOKE)
    file(GLOB d2e_generated_sources CONFIGURE_DEPENDS
        "generated/xtensa-asm-smoke/*.c"
        "generated/xtensa-asm-smoke/*.S")
    if(NOT d2e_generated_sources)
        message(FATAL_ERROR "Generate Xtensa assembly smoke sources before configuring")
    endif()
elseif(NOT D2E_XIP_SHELL)
    set(d2e_generated_sources "generated/native_smoke.c")
endif()

idf_component_register(
    SRCS
        ${d2e_entry_source}
        "cyd_flash.c"
        "cyd_sd.c"
        "cyd_display.c"
        "pc_speaker_audio.c"
        "qemu_frame_dump.c"
        ${d2e_generated_sources}
        "${d2e_root}/src/core/native_runtime.c"
        "${d2e_root}/src/core/native_helpers.c"
        "${d2e_root}/src/core/native_patterns.c"
        "${d2e_root}/src/core/package.c"
        "${d2e_root}/src/core/supervisor.c"
        "${d2e_root}/src/core/x86_alu.c"
        "${d2e_root}/src/core/x86_control.c"
        "${d2e_root}/src/core/x86_cpu.c"
        "${d2e_root}/src/core/x86_memory.c"
        "${d2e_root}/src/core/xip_module.c"
        "${d2e_root}/src/core/xip_imports.c"
        "${d2e_root}/src/devices/cga.c"
        "${d2e_root}/src/devices/cp437_font.c"
        "${d2e_root}/src/devices/pc_speaker.c"
        "${d2e_root}/src/devices/text_video.c"
        "${d2e_root}/src/machine/pc_at.c"
        "${d2e_root}/src/machine/pc_input.c"
        "${d2e_root}/src/shell/shell.c"
    INCLUDE_DIRS
        "."
        "${d2e_root}/include"
    REQUIRES
        esp_driver_dac
        esp_driver_gpio
        esp_driver_sdspi
        esp_driver_spi
        esp_driver_uart
        esp_lcd
        esp_timer
        esp_system
        freertos
        fatfs
        heap
        mbedtls
        esp_partition
        sdmmc
        vfs
)

target_compile_options(${COMPONENT_LIB} PRIVATE -O3 -Wall -Wextra -Werror)
if(D2E_QEMU_SMOKE)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE D2E_QEMU_SMOKE=1)
endif()
if(D2E_QEMU_BOARD_DEVICES)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        D2E_QEMU_BOARD_DEVICES=1)
endif()
if(D2E_QEMU_INTERACTIVE)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        D2E_QEMU_INTERACTIVE=1
        D2E_QEMU_INTERACTIVE_FRAME_LIMIT=${D2E_QEMU_INTERACTIVE_FRAME_LIMIT}
    )
endif()
if(D2E_QEMU_DUMP_FRAME)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE D2E_QEMU_DUMP_FRAME=1)
endif()
if(D2E_QEMU_SCRIPTED_INPUT)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        D2E_QEMU_SCRIPTED_INPUT=1
    )
endif()
if(D2E_QEMU_EXIT_AFTER_RETURN)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        D2E_QEMU_EXIT_AFTER_RETURN=1
    )
endif()
if(D2E_ALLEY_CAT)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE D2E_ALLEY_CAT=1)
endif()
if(D2E_XTENSA_ASM_SMOKE)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE D2E_XTENSA_ASM_SMOKE=1)
endif()
if(D2E_SHELL_AUTORUN)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE D2E_SHELL_AUTORUN=1)
endif()
if(D2E_XIP_SHELL)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE D2E_XIP_SHELL=1)
endif()
if(D2E_QEMU_XIP_INSTALL_FILE)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        D2E_QEMU_XIP_INSTALL_FILE="${D2E_QEMU_XIP_INSTALL_FILE}")
endif()
