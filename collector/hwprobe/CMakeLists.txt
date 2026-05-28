cmake_minimum_required(VERSION 3.16)
project(auditcore_hwprobe CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_compile_options(-Wall -Wextra -Wpedantic -Werror=return-type)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

find_package(PkgConfig REQUIRED)

# hwloc: required. CPU topology, NUMA nodes, caches, PCI tree.
pkg_check_modules(HWLOC REQUIRED hwloc)

# libsensors: optional. Thermals and fan speeds.
pkg_check_modules(SENSORS QUIET libsensors)

# NVML: optional. NVIDIA GPU inventory + health.
find_library(NVML_LIB NAMES nvidia-ml)

add_executable(hwprobe
    src/main.cpp
    src/topology.cpp
    src/json_writer.cpp
)

target_include_directories(hwprobe PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${HWLOC_INCLUDE_DIRS}
)
target_link_libraries(hwprobe PRIVATE ${HWLOC_LIBRARIES})
target_link_directories(hwprobe PRIVATE ${HWLOC_LIBRARY_DIRS})

if(SENSORS_FOUND)
    message(STATUS "libsensors found — enabling thermals")
    target_compile_definitions(hwprobe PRIVATE AC_HAVE_SENSORS=1)
    target_include_directories(hwprobe PRIVATE ${SENSORS_INCLUDE_DIRS})
    target_link_libraries(hwprobe PRIVATE ${SENSORS_LIBRARIES})
    target_sources(hwprobe PRIVATE src/sensors.cpp)
else()
    message(STATUS "libsensors NOT found — thermals disabled")
endif()

if(NVML_LIB)
    message(STATUS "NVML found at ${NVML_LIB} — enabling GPU inventory")
    target_compile_definitions(hwprobe PRIVATE AC_HAVE_NVML=1)
    target_link_libraries(hwprobe PRIVATE ${NVML_LIB})
    target_sources(hwprobe PRIVATE src/nvml.cpp)
else()
    message(STATUS "NVML NOT found — NVIDIA GPU inventory disabled")
endif()

install(TARGETS hwprobe RUNTIME DESTINATION bin)
