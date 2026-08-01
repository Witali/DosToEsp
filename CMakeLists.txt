cmake_minimum_required(VERSION 3.20)
project(DosToEsp VERSION 0.1.0 LANGUAGES C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

add_library(d2e_core
    src/devices/cga.c
    src/devices/cp437_font.c
    src/devices/pc_speaker.c
    src/devices/text_video.c
    src/machine/pc_at.c
    src/machine/pc_input.c
    src/core/native_runtime.c
    src/core/native_patterns.c
    src/core/package.c
    src/core/supervisor.c
    src/core/x86_alu.c
    src/core/x86_cpu.c
    src/core/x86_memory.c
)
target_include_directories(d2e_core PUBLIC include)

if(MSVC)
    target_compile_options(d2e_core PRIVATE /W4 /WX)
else()
    target_compile_options(d2e_core PRIVATE
        -Wall -Wextra -Wpedantic -Werror
    )
endif()

include(CTest)
if(BUILD_TESTING)
    add_executable(d2e_core_tests tests/test_core.c)
    target_link_libraries(d2e_core_tests PRIVATE d2e_core)
    if(MSVC)
        target_compile_options(d2e_core_tests PRIVATE /W4 /WX)
    else()
        target_compile_options(d2e_core_tests PRIVATE
            -Wall -Wextra -Wpedantic -Werror
        )
    endif()
    add_test(NAME d2e_core_tests COMMAND d2e_core_tests)

    add_executable(d2e_supervisor_tests tests/test_supervisor.c)
    target_link_libraries(d2e_supervisor_tests PRIVATE d2e_core)
    if(MSVC)
        target_compile_options(d2e_supervisor_tests PRIVATE /W4 /WX)
    else()
        target_compile_options(d2e_supervisor_tests PRIVATE
            -Wall -Wextra -Wpedantic -Werror
        )
    endif()
    add_test(NAME d2e_supervisor_tests COMMAND d2e_supervisor_tests)

    add_executable(d2e_native_patterns_tests tests/test_native_patterns.c)
    target_link_libraries(d2e_native_patterns_tests PRIVATE d2e_core)
    if(MSVC)
        target_compile_options(d2e_native_patterns_tests PRIVATE /W4 /WX)
    else()
        target_compile_options(d2e_native_patterns_tests PRIVATE
            -Wall -Wextra -Wpedantic -Werror
        )
    endif()
    add_test(NAME d2e_native_patterns_tests COMMAND d2e_native_patterns_tests)

    add_executable(d2e_cga_tests tests/test_cga.c)
    target_link_libraries(d2e_cga_tests PRIVATE d2e_core)
    if(MSVC)
        target_compile_options(d2e_cga_tests PRIVATE /W4 /WX)
    else()
        target_compile_options(d2e_cga_tests PRIVATE
            -Wall -Wextra -Wpedantic -Werror
        )
    endif()
    add_test(NAME d2e_cga_tests COMMAND d2e_cga_tests)

    add_executable(d2e_text_video_tests tests/test_text_video.c)
    target_link_libraries(d2e_text_video_tests PRIVATE d2e_core)
    if(MSVC)
        target_compile_options(d2e_text_video_tests PRIVATE /W4 /WX)
    else()
        target_compile_options(d2e_text_video_tests PRIVATE
            -Wall -Wextra -Wpedantic -Werror
        )
    endif()
    add_test(NAME d2e_text_video_tests COMMAND d2e_text_video_tests)

    add_executable(d2e_pc_speaker_tests tests/test_pc_speaker.c)
    target_link_libraries(d2e_pc_speaker_tests PRIVATE d2e_core)
    if(MSVC)
        target_compile_options(d2e_pc_speaker_tests PRIVATE /W4 /WX)
    else()
        target_compile_options(d2e_pc_speaker_tests PRIVATE
            -Wall -Wextra -Wpedantic -Werror
        )
    endif()
    add_test(NAME d2e_pc_speaker_tests COMMAND d2e_pc_speaker_tests)

    add_executable(d2e_pc_at_tests tests/test_pc_at.c)
    target_link_libraries(d2e_pc_at_tests PRIVATE d2e_core)
    if(MSVC)
        target_compile_options(d2e_pc_at_tests PRIVATE /W4 /WX)
    else()
        target_compile_options(d2e_pc_at_tests PRIVATE
            -Wall -Wextra -Wpedantic -Werror
        )
    endif()
    add_test(NAME d2e_pc_at_tests COMMAND d2e_pc_at_tests)

    add_executable(d2e_pc_input_tests tests/test_pc_input.c)
    target_link_libraries(d2e_pc_input_tests PRIVATE d2e_core)
    if(MSVC)
        target_compile_options(d2e_pc_input_tests PRIVATE /W4 /WX)
    else()
        target_compile_options(d2e_pc_input_tests PRIVATE
            -Wall -Wextra -Wpedantic -Werror
        )
    endif()
    add_test(NAME d2e_pc_input_tests COMMAND d2e_pc_input_tests)

    add_executable(d2e_loader_tests tests/test_loader.c)
    target_link_libraries(d2e_loader_tests PRIVATE d2e_core)
    if(MSVC)
        target_compile_options(d2e_loader_tests PRIVATE /W4 /WX)
    else()
        target_compile_options(d2e_loader_tests PRIVATE
            -Wall -Wextra -Wpedantic -Werror
        )
    endif()
    add_test(NAME d2e_loader_tests COMMAND d2e_loader_tests)

    set(D2E_PYTHON "" CACHE FILEPATH "Python used by the host translator")
    set(D2E_ALLEY_CAT_EXE "" CACHE FILEPATH "Optional local Alley Cat MZ image")
    if(D2E_PYTHON)
        set(D2E_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
        set(D2E_SMOKE_C "${D2E_GENERATED_DIR}/native_smoke.c")
        add_custom_command(
            OUTPUT "${D2E_SMOKE_C}"
            COMMAND "${D2E_PYTHON}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/d2e_translate.py"
                    --hex-input --name native_smoke
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/native_smoke.hex"
                    "${D2E_SMOKE_C}"
            DEPENDS
                tools/d2e_translate.py
                tests/fixtures/native_smoke.hex
            VERBATIM
        )
        add_executable(d2e_native_tests
            tests/test_native.c
            "${D2E_SMOKE_C}"
        )
        target_link_libraries(d2e_native_tests PRIVATE d2e_core)
        if(MSVC)
            target_compile_options(d2e_native_tests PRIVATE /W4 /WX)
        else()
            target_compile_options(d2e_native_tests PRIVATE
                -Wall -Wextra -Wpedantic -Werror
            )
        endif()
        add_test(NAME d2e_native_tests COMMAND d2e_native_tests)

        set(D2E_MEMORY_C "${D2E_GENERATED_DIR}/native_memory.c")
        add_custom_command(
            OUTPUT "${D2E_MEMORY_C}"
            COMMAND "${D2E_PYTHON}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/d2e_translate.py"
                    --hex-input --name native_memory
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/native_memory.hex"
                    "${D2E_MEMORY_C}"
            DEPENDS
                tools/d2e_translate.py
                tests/fixtures/native_memory.hex
            VERBATIM
        )
        add_executable(d2e_native_memory_tests
            tests/test_native_memory.c
            "${D2E_MEMORY_C}"
        )
        target_link_libraries(d2e_native_memory_tests PRIVATE d2e_core)
        if(MSVC)
            target_compile_options(d2e_native_memory_tests PRIVATE /W4 /WX)
        else()
            target_compile_options(d2e_native_memory_tests PRIVATE
                -Wall -Wextra -Wpedantic -Werror
            )
        endif()
        add_test(NAME d2e_native_memory_tests COMMAND d2e_native_memory_tests)

        set(D2E_CALL_C "${D2E_GENERATED_DIR}/native_call.c")
        add_custom_command(
            OUTPUT "${D2E_CALL_C}"
            COMMAND "${D2E_PYTHON}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/d2e_translate.py"
                    --hex-input --name native_call
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/native_call.hex"
                    "${D2E_CALL_C}"
            DEPENDS
                tools/d2e_translate.py
                tests/fixtures/native_call.hex
            VERBATIM
        )
        add_executable(d2e_native_call_tests
            tests/test_native_call.c
            "${D2E_CALL_C}"
        )
        target_link_libraries(d2e_native_call_tests PRIVATE d2e_core)
        if(MSVC)
            target_compile_options(d2e_native_call_tests PRIVATE /W4 /WX)
        else()
            target_compile_options(d2e_native_call_tests PRIVATE
                -Wall -Wextra -Wpedantic -Werror
            )
        endif()
        add_test(NAME d2e_native_call_tests COMMAND d2e_native_call_tests)

        set(D2E_LOGIC_C "${D2E_GENERATED_DIR}/native_logic.c")
        add_custom_command(
            OUTPUT "${D2E_LOGIC_C}"
            COMMAND "${D2E_PYTHON}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/d2e_translate.py"
                    --hex-input --name native_logic
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/native_logic.hex"
                    "${D2E_LOGIC_C}"
            DEPENDS
                tools/d2e_translate.py
                tests/fixtures/native_logic.hex
            VERBATIM
        )
        add_executable(d2e_native_logic_tests
            tests/test_native_logic.c
            "${D2E_LOGIC_C}"
        )
        target_link_libraries(d2e_native_logic_tests PRIVATE d2e_core)
        if(MSVC)
            target_compile_options(d2e_native_logic_tests PRIVATE /W4 /WX)
        else()
            target_compile_options(d2e_native_logic_tests PRIVATE
                -Wall -Wextra -Wpedantic -Werror
            )
        endif()
        add_test(NAME d2e_native_logic_tests COMMAND d2e_native_logic_tests)

        set(D2E_SHIFT_C "${D2E_GENERATED_DIR}/native_shift.c")
        add_custom_command(
            OUTPUT "${D2E_SHIFT_C}"
            COMMAND "${D2E_PYTHON}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/d2e_translate.py"
                    --hex-input --name native_shift
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/native_shift.hex"
                    "${D2E_SHIFT_C}"
            DEPENDS
                tools/d2e_translate.py
                tests/fixtures/native_shift.hex
            VERBATIM
        )
        add_executable(d2e_native_shift_tests
            tests/test_native_shift.c
            "${D2E_SHIFT_C}"
        )
        target_link_libraries(d2e_native_shift_tests PRIVATE d2e_core)
        if(MSVC)
            target_compile_options(d2e_native_shift_tests PRIVATE /W4 /WX)
        else()
            target_compile_options(d2e_native_shift_tests PRIVATE
                -Wall -Wextra -Wpedantic -Werror
            )
        endif()
        add_test(NAME d2e_native_shift_tests COMMAND d2e_native_shift_tests)

        set(D2E_STRING_C "${D2E_GENERATED_DIR}/native_string.c")
        add_custom_command(
            OUTPUT "${D2E_STRING_C}"
            COMMAND "${D2E_PYTHON}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/d2e_translate.py"
                    --hex-input --name native_string
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/native_string.hex"
                    "${D2E_STRING_C}"
            DEPENDS
                tools/d2e_translate.py
                tests/fixtures/native_string.hex
            VERBATIM
        )
        add_executable(d2e_native_string_tests
            tests/test_native_string.c
            "${D2E_STRING_C}"
        )
        target_link_libraries(d2e_native_string_tests PRIVATE d2e_core)
        if(MSVC)
            target_compile_options(d2e_native_string_tests PRIVATE /W4 /WX)
        else()
            target_compile_options(d2e_native_string_tests PRIVATE
                -Wall -Wextra -Wpedantic -Werror
            )
        endif()
        add_test(NAME d2e_native_string_tests COMMAND d2e_native_string_tests)

        set(D2E_IRQ_C "${D2E_GENERATED_DIR}/native_irq.c")
        add_custom_command(
            OUTPUT "${D2E_IRQ_C}"
            COMMAND "${D2E_PYTHON}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/d2e_translate.py"
                    --hex-input --name native_irq
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/native_irq.hex"
                    "${D2E_IRQ_C}"
            DEPENDS
                tools/d2e_translate.py
                tests/fixtures/native_irq.hex
            VERBATIM
        )
        add_executable(d2e_native_irq_tests
            tests/test_native_irq.c
            "${D2E_IRQ_C}"
        )
        target_link_libraries(d2e_native_irq_tests PRIVATE d2e_core)
        if(MSVC)
            target_compile_options(d2e_native_irq_tests PRIVATE /W4 /WX)
        else()
            target_compile_options(d2e_native_irq_tests PRIVATE
                -Wall -Wextra -Wpedantic -Werror
            )
        endif()
        add_test(NAME d2e_native_irq_tests COMMAND d2e_native_irq_tests)

        set(D2E_PORT_C "${D2E_GENERATED_DIR}/native_port.c")
        add_custom_command(
            OUTPUT "${D2E_PORT_C}"
            COMMAND "${D2E_PYTHON}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/d2e_translate.py"
                    --hex-input --name native_port
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/native_port.hex"
                    "${D2E_PORT_C}"
            DEPENDS
                tools/d2e_translate.py
                tests/fixtures/native_port.hex
            VERBATIM
        )
        add_executable(d2e_native_port_tests
            tests/test_native_port.c
            "${D2E_PORT_C}"
        )
        target_link_libraries(d2e_native_port_tests PRIVATE d2e_core)
        if(MSVC)
            target_compile_options(d2e_native_port_tests PRIVATE /W4 /WX)
        else()
            target_compile_options(d2e_native_port_tests PRIVATE
                -Wall -Wextra -Wpedantic -Werror
            )
        endif()
        add_test(NAME d2e_native_port_tests COMMAND d2e_native_port_tests)

        set(D2E_RARE_C "${D2E_GENERATED_DIR}/native_rare.c")
        add_custom_command(
            OUTPUT "${D2E_RARE_C}"
            COMMAND "${D2E_PYTHON}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/d2e_translate.py"
                    --hex-input --name native_rare
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/native_rare.hex"
                    "${D2E_RARE_C}"
            DEPENDS
                tools/d2e_translate.py
                tests/fixtures/native_rare.hex
            VERBATIM
        )
        add_executable(d2e_native_rare_tests
            tests/test_native_rare.c
            "${D2E_RARE_C}"
        )
        target_link_libraries(d2e_native_rare_tests PRIVATE d2e_core)
        if(MSVC)
            target_compile_options(d2e_native_rare_tests PRIVATE /W4 /WX)
        else()
            target_compile_options(d2e_native_rare_tests PRIVATE
                -Wall -Wextra -Wpedantic -Werror
            )
        endif()
        add_test(NAME d2e_native_rare_tests COMMAND d2e_native_rare_tests)

        set(D2E_INDIRECT_C "${D2E_GENERATED_DIR}/native_indirect.c")
        add_custom_command(
            OUTPUT "${D2E_INDIRECT_C}"
            COMMAND "${D2E_PYTHON}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/d2e_translate.py"
                    --hex-input --name native_indirect
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/native_indirect.hex"
                    "${D2E_INDIRECT_C}"
            DEPENDS
                tools/d2e_translate.py
                tests/fixtures/native_indirect.hex
            VERBATIM
        )
        add_executable(d2e_native_indirect_tests
            tests/test_native_indirect.c
            "${D2E_INDIRECT_C}"
        )
        target_link_libraries(d2e_native_indirect_tests PRIVATE d2e_core)
        if(MSVC)
            target_compile_options(d2e_native_indirect_tests PRIVATE /W4 /WX)
        else()
            target_compile_options(d2e_native_indirect_tests PRIVATE
                -Wall -Wextra -Wpedantic -Werror
            )
        endif()
        add_test(NAME d2e_native_indirect_tests COMMAND d2e_native_indirect_tests)

        set(D2E_ADC_FLAGS_C "${D2E_GENERATED_DIR}/native_adc_flags.c")
        add_custom_command(
            OUTPUT "${D2E_ADC_FLAGS_C}"
            COMMAND "${D2E_PYTHON}"
                    "${CMAKE_CURRENT_SOURCE_DIR}/tools/d2e_translate.py"
                    --hex-input --name native_adc_flags
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/native_adc_flags.hex"
                    "${D2E_ADC_FLAGS_C}"
            DEPENDS
                tools/d2e_translate.py
                tests/fixtures/native_adc_flags.hex
            VERBATIM
        )
        add_executable(d2e_native_adc_flags_tests
            tests/test_native_adc_flags.c
            "${D2E_ADC_FLAGS_C}"
        )
        target_link_libraries(d2e_native_adc_flags_tests PRIVATE d2e_core)
        if(MSVC)
            target_compile_options(d2e_native_adc_flags_tests PRIVATE /W4 /WX)
        else()
            target_compile_options(d2e_native_adc_flags_tests PRIVATE
                -Wall -Wextra -Wpedantic -Werror
            )
        endif()
        add_test(NAME d2e_native_adc_flags_tests COMMAND d2e_native_adc_flags_tests)

        if(D2E_ALLEY_CAT_EXE AND EXISTS "${D2E_ALLEY_CAT_EXE}")
            set(D2E_ALLEY_CAT_C "${D2E_GENERATED_DIR}/alley_cat_image.c")
            add_custom_command(
                OUTPUT "${D2E_ALLEY_CAT_C}"
                COMMAND "${D2E_PYTHON}"
                        "${CMAKE_CURRENT_SOURCE_DIR}/tools/d2e_pack_mz.py"
                        --name alley_cat
                        "${D2E_ALLEY_CAT_EXE}"
                        "${D2E_ALLEY_CAT_C}"
                DEPENDS
                    tools/d2e_pack_mz.py
                    tools/d2e_analyze.py
                    "${D2E_ALLEY_CAT_EXE}"
                VERBATIM
            )
            add_executable(d2e_mz_image_tests
                tests/test_mz_image.c
                "${D2E_ALLEY_CAT_C}"
            )
            target_link_libraries(d2e_mz_image_tests PRIVATE d2e_core)
            if(MSVC)
                target_compile_options(d2e_mz_image_tests PRIVATE /W4 /WX)
            else()
                target_compile_options(d2e_mz_image_tests PRIVATE
                    -Wall -Wextra -Wpedantic -Werror
                )
            endif()
            add_test(NAME d2e_mz_image_tests COMMAND d2e_mz_image_tests)
        endif()
    endif()
endif()
