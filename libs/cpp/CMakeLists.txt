add_library(daq_alert_cpp STATIC src/daq_alert.cpp)

target_include_directories(daq_alert_cpp
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)

# Inherit the C header search path and any platform link libraries
target_link_libraries(daq_alert_cpp PUBLIC daq_alert_c)

set_target_properties(daq_alert_cpp PROPERTIES OUTPUT_NAME daq_alert_cpp)

install(TARGETS daq_alert_cpp
    EXPORT  mu2e_daq_alert_targets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)

install(FILES include/daq_alert.hpp
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
