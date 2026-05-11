install(
    PROGRAMS ${CMAKE_CURRENT_SOURCE_DIR}/example-sender-py
    DESTINATION ${CMAKE_INSTALL_BINDIR}
)
install(
    FILES example-sender-py.1
    DESTINATION ${CMAKE_INSTALL_MANDIR}/man1
)
