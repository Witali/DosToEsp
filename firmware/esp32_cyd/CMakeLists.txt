cmake_minimum_required(VERSION 3.16)

if(D2E_ALLEY_CAT)
    set_property(GLOBAL PROPERTY JOB_POOLS d2e_compile_pool=1)
    set(CMAKE_JOB_POOL_COMPILE d2e_compile_pool)
endif()

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(dostoesp_native_smoke C)
