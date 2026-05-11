find_package(Python3 REQUIRED COMPONENTS Interpreter)

# Determine the target site-packages directory.
# Override by passing -DDAQ_ALERT_PYTHON_INSTALL_DIR=<path> to cmake.
if(DEFINED DAQ_ALERT_PYTHON_INSTALL_DIR)
    set(_py_dest ${DAQ_ALERT_PYTHON_INSTALL_DIR})
else()
    execute_process(
        COMMAND "${Python3_EXECUTABLE}" -c
            "import sysconfig; print(sysconfig.get_path('purelib'))"
        OUTPUT_VARIABLE _py_dest
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE _py_rc
    )
    if(NOT _py_rc EQUAL 0)
        message(FATAL_ERROR "Could not determine Python site-packages directory. "
            "Set DAQ_ALERT_PYTHON_INSTALL_DIR manually.")
    endif()
endif()

message(STATUS "Python daq_alert package install dir: ${_py_dest}")

install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/daq_alert
    DESTINATION ${_py_dest}
    FILES_MATCHING PATTERN "*.py"
)
