add_executable(example-sender-cpp main.cpp)
target_link_libraries(example-sender-cpp PRIVATE daq_alert_cpp)

install(TARGETS example-sender-cpp RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES example-sender-cpp.1 DESTINATION ${CMAKE_INSTALL_MANDIR}/man1)
