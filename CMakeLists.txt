cmake_minimum_required(VERSION 3.20)
project(DosToEsp VERSION 0.1.0 LANGUAGES C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

add_library(d2e_core
    src/core/native_runtime.c
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

    set(D2E_PYTHON "" CACHE FILEPATH "Python used by the host translator")
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
    endif()
endif()
