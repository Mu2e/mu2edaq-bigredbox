add_executable(example-sender-c main.c)
target_link_libraries(example-sender-c PRIVATE daq_alert_c)

install(TARGETS example-sender-c RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES example-sender-c.1 DESTINATION ${CMAKE_INSTALL_MANDIR}/man1)
