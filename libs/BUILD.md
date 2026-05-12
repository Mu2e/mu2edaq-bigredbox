# Building the mu2e DAQ Alert Libraries

Three libraries are provided under `libs/` — C, C++, and Python — all implementing
the same UDP broadcast protocol used by the `daq_alert` daemon.

## Prerequisites

| Requirement | Minimum version |
|---|---|
| CMake | 3.15 |
| C compiler | C99 |
| C++ compiler | C++17 |
| Python | 3.9 (Python library only) |

## Quick start

```bash
cd libs
cmake -B build -DCMAKE_INSTALL_PREFIX=./install
cmake --build build
cmake --install build
```

Installed artifacts:

```
install/
├── bin/
│   ├── example-sender-c
│   ├── example-sender-cpp
│   └── example-sender-py
├── include/
│   ├── daq_alert.h          # C header
│   └── daq_alert.hpp        # C++ header
├── lib/
│   ├── libdaq_alert.a       # C static library
│   └── libdaq_alert_cpp.a   # C++ static library
├── man/
│   └── man1/
│       ├── example-sender-c.1
│       ├── example-sender-cpp.1
│       └── example-sender-py.1
└── python/                  # only when DAQ_ALERT_PYTHON_INSTALL_DIR is set
    └── daq_alert/
        ├── __init__.py
        └── _sender.py
```

## CMake options

| Option | Default | Description |
|---|---|---|
| `CMAKE_INSTALL_PREFIX` | `/usr/local` | Root installation directory |
| `CMAKE_BUILD_TYPE` | `Release` | `Release`, `Debug`, `RelWithDebInfo` |
| `DAQ_ALERT_PYTHON_INSTALL_DIR` | system site-packages | Override Python install path |
| `BUILD_SHARED_LIBS` | `OFF` | Build shared libraries instead of static |

## C library

### Linking

```cmake
target_link_libraries(my_app PRIVATE daq_alert_c)
target_include_directories(my_app PRIVATE /path/to/install/include)
```

Or with a manual compile command:

```bash
gcc my_app.c -I./install/include -L./install/lib -ldaq_alert -o my_app
```

### Usage

```c
#include "daq_alert.h"

/* NULL and 0 use defaults: 255.255.255.255 and port 37020 */
DaqAlertResult rc = daq_alert_send("DAQ-NODE-01", "Buffer overflow", NULL, 0);
if (rc != DAQ_ALERT_OK)
    fprintf(stderr, "alert failed: %s\n", daq_alert_strerror(rc));

/* Custom destination */
rc = daq_alert_send("DAQ-NODE-01", "Buffer overflow", "192.168.1.255", 37020);
```

## C++ library

The C++ library wraps the C library, so link against both:

### Linking

```cmake
target_link_libraries(my_app PRIVATE daq_alert_cpp)   # pulls in daq_alert_c transitively
target_include_directories(my_app PRIVATE /path/to/install/include)
```

```bash
g++ my_app.cpp -I./install/include -L./install/lib -ldaq_alert_cpp -ldaq_alert -o my_app
```

### Usage

```cpp
#include "daq_alert.hpp"

// Reusable sender — configure once, call send() as often as needed
mu2e::daq::AlertSender sender;                         // defaults
mu2e::daq::AlertSender sender("192.168.1.255", 37020); // explicit

sender.send("DAQ-NODE-01", "Buffer overflow");         // throws mu2e::daq::AlertError on failure

// One-shot free function
mu2e::daq::AlertSender::send_once("DAQ-NODE-01", "Buffer overflow");
```

## Python library

### Installation via CMake

By default CMake installs to the active Python interpreter's site-packages:

```bash
cmake -B build
cmake --build build
cmake --install build
```

To install to a custom directory instead (e.g. inside a virtual environment):

```bash
cmake -B build -DDAQ_ALERT_PYTHON_INSTALL_DIR=/path/to/venv/lib/python3.x/site-packages
cmake --install build
```

### Installation via pip (standalone)

Activate your virtual environment first, then install from the repo root:

```bash
pip install libs/python/
```

### Usage

```python
from daq_alert import send_alert, AlertSender

# Free function — send once and forget
send_alert("DAQ-NODE-01", "Buffer overflow")
send_alert("DAQ-NODE-01", "Buffer overflow", broadcast_ip="192.168.1.255", port=37020)

# Reusable sender
sender = AlertSender("192.168.1.255")
sender.send("DAQ-NODE-01", "Buffer overflow")
```

## Shared libraries

The build produces static libraries by default.  To build shared libraries instead:

```bash
cmake -B build -DBUILD_SHARED_LIBS=ON
```

## Platform notes

**macOS / Linux** — no extra dependencies beyond a standard compiler toolchain.

**Windows** — the C and C++ libraries link against `ws2_32` automatically via CMake.
Use a Visual Studio generator or MinGW and ensure `winsock2.h` is available.
