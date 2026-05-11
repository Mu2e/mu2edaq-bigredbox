add_library(daq_alert_c STATIC src/daq_alert.c)

target_include_directories(daq_alert_c
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)

if(WIN32)
    target_link_libraries(daq_alert_c PUBLIC ws2_32)
endif()

set_target_properties(daq_alert_c PROPERTIES OUTPUT_NAME daq_alert)

install(TARGETS daq_alert_c
    EXPORT  mu2e_daq_alert_targets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)

install(FILES include/daq_alert.h
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
