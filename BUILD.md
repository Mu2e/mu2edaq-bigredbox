# Build and Installation

This repository contains two independently buildable components:

| Component | Language | Build system |
|---|---|---|
| DAQ alert daemon | Python + PyQt5 | — (run directly) |
| Alert-sender libraries and examples | C, C++, Python | CMake |

---

## DAQ alert daemon

### Requirements

- Python 3.9 or later
- A running X11/Wayland display (`DISPLAY` must be set)

### Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt   # installs PyQt5>=5.15
```

### Running

```bash
# Start as a background daemon (logs to /tmp/daq_alert.log)
./start_daq_alert.sh

# Stop the daemon
./stop_daq_alert.sh

# Send a test alert to verify the GUI
python3 demo_sender.py
python3 demo_sender.py --system-id "DAQ-NODE-03" --message "Readout buffer overflow"
```

---

## Alert-sender libraries

Three libraries under `libs/` share the same UDP broadcast protocol as the daemon.

### Requirements

| Requirement | Minimum version |
|---|---|
| CMake | 3.15 |
| C compiler | C99 |
| C++ compiler | C++17 |
| Python | 3.9 (Python library and example only) |

### Build

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

### CMake options

| Option | Default | Description |
|---|---|---|
| `CMAKE_INSTALL_PREFIX` | `/usr/local` | Root installation directory |
| `CMAKE_BUILD_TYPE` | `Release` | `Release`, `Debug`, `RelWithDebInfo` |
| `DAQ_ALERT_PYTHON_INSTALL_DIR` | system site-packages | Override Python package install path |
| `BUILD_SHARED_LIBS` | `OFF` | Build shared libraries instead of static |

To install the Python library to a virtual environment instead of system site-packages:

```bash
cmake -B build \
    -DDAQ_ALERT_PYTHON_INSTALL_DIR="$(python3 -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"
cmake --install build
```

---

## Example senders

The three example programs are built automatically as part of the CMake build above.
After installation they are available on `PATH` as `example-sender-c`,
`example-sender-cpp`, and `example-sender-py`.  Each accepts the same flags:

| Flag | Default | Description |
|---|---|---|
| `-s`, `--system-id` | `DAQ-NODE-01` | System identifier |
| `-m`, `--message` | *(library-specific default)* | Alert message text |
| `-i`, `--ip` | `255.255.255.255` | UDP broadcast destination |
| `-p`, `--port` | `37020` | UDP port |
| `-h`, `--help` | — | Print usage and exit |

```bash
example-sender-c --system-id DAQ-NODE-03 --message "Buffer overflow"
example-sender-cpp --ip 192.168.1.255 --port 37020
example-sender-py --system-id DAQ-NODE-03 --message "Buffer overflow"
```

Man pages are installed to `<prefix>/man/man1/` and can be read with:

```bash
man ./install/man/man1/example-sender-c.1
man ./install/man/man1/example-sender-cpp.1
man ./install/man/man1/example-sender-py.1
```

---

## Python library — standalone install

The Python library can be installed independently of CMake via pip.
Activate your virtual environment first, then:

```bash
pip install libs/python/
```

Usage:

```python
from daq_alert import send_alert, AlertSender

send_alert("DAQ-NODE-01", "Buffer overflow")

sender = AlertSender("192.168.1.255")
sender.send("DAQ-NODE-01", "Buffer overflow")
```

---

## Using the C and C++ libraries in your own project

### C

```c
#include "daq_alert.h"

DaqAlertResult rc = daq_alert_send("DAQ-NODE-01", "Buffer overflow", NULL, 0);
if (rc != DAQ_ALERT_OK)
    fprintf(stderr, "%s\n", daq_alert_strerror(rc));
```

Link flags: `-ldaq_alert`

### C++

```cpp
#include "daq_alert.hpp"

try {
    mu2e::daq::AlertSender sender;
    sender.send("DAQ-NODE-01", "Buffer overflow");
} catch (const mu2e::daq::AlertError &e) {
    std::cerr << e.what() << "\n";
}
```

Link flags: `-ldaq_alert_cpp -ldaq_alert`

### CMake consumers

```cmake
find_library(DAQ_ALERT_C   daq_alert     HINTS /path/to/install/lib)
find_library(DAQ_ALERT_CPP daq_alert_cpp HINTS /path/to/install/lib)

target_link_libraries(my_target PRIVATE ${DAQ_ALERT_CPP} ${DAQ_ALERT_C})
target_include_directories(my_target PRIVATE /path/to/install/include)
```
