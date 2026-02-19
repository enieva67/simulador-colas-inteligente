cmake_minimum_required(VERSION 3.10)
project(DemoCppPython)

# ¡FORZAR MODO ULTRA RÁPIDO!
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# 1. Buscar y configurar Python
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)

# 2. Descargar pybind11 automáticamente desde internet (Modern CMake)
include(FetchContent)
FetchContent_Declare(
  pybind11
  GIT_REPOSITORY https://github.com/pybind/pybind11.git
  GIT_TAG        v2.11.1
)
FetchContent_MakeAvailable(pybind11)

# 3. Crear el módulo
# "super_cpp" debe coincidir con el nombre dentro del PYBIND11_MODULE en el .cpp
pybind11_add_module(super_cpp mi_modulo.cpp)

# 4. Ajustes finales (opcional, pero útil para depurar)
# Esto asegura que las librerías se guarden donde está tu código fuente
set_target_properties(super_cpp PROPERTIES LIBRARY_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR})