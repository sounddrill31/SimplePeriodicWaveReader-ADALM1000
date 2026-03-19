"""
Hello‑world script for ADALM1000 using libsmu (pysmu).
https://analogdevicesinc.github.io/libsmu/index.html#reading_data
Python Equivalent for C++ example from the Analog Devices libsmu docs into Python.
"""

import time
import pysmu

# Create session and add all compatible devices (equivalent to session->add_all())
session = pysmu.Session(add_all=True)

# Grab the first device (equivalent to *(session->m_devices.begin()))
if not session.devices:
    print("No ADALM1000 device found!")
    exit(1)
dev = session.devices[0]

# Configure at default device rate and start continuous mode (equivalent to
# session->configure(dev->get_default_rate()) and session->start(0))
session.configure(dev.get_default_rate())
session.start(continuous=True)

# Read in a loop, printing all four values per sample.
# Each sample is a tuple: (A_voltage, A_current, B_voltage, B_current)
try:
    while True:
        # Read 1024 samples at a time; note timeout is 0 (non‑blocking) so
        # actual returned count may be less.  This corresponds to the C++
        # `dev->read(buf, 1024);` example.
        samples = dev.get_samples(1024)

        # Iterate over all returned samples (may be fewer than 1024).
        for a_v, a_i, b_v, b_i in samples:
            print(f"Channel A: Voltage {a_v:.6f} V, Current {a_i:.6f} A")
            print(f"Channel B: Voltage {b_v:.6f} V, Current {b_i:.6f} A")

        # Optional: throttle printing to avoid issues
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nStopping ADALM1000 read loop.")
    session.stop()
