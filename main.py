"""
Frequency measurement script for ADALM1000 using libsmu (pysmu).
https://analogdevicesinc.github.io/libsmu/index.html#reading_data_from_a_device

Detects peaks in the Channel A voltage signal and calculates frequency
using F = 1/T, where T is the period derived from the number of samples
between consecutive peaks and the device sample rate.
"""

import pysmu

# Only report peaks whose voltage is above this absolute level.
# Raise this if you see false peaks from noise; lower it for small signals.
MIN_PEAK_HEIGHT = 0.1  # volts


def find_peaks(voltages):
    """Return indices of local maxima in *voltages* that are also above
    MIN_PEAK_HEIGHT.

    A sample at index i is a peak when:
        voltages[i] > voltages[i-1]  and  voltages[i] > voltages[i+1]
        and voltages[i] >= MIN_PEAK_HEIGHT
    """
    peaks = []
    for i in range(1, len(voltages) - 1):
        if (
            voltages[i] > voltages[i - 1]
            and voltages[i] > voltages[i + 1]
            and voltages[i] >= MIN_PEAK_HEIGHT
        ):
            peaks.append(i)
    return peaks


# Create session and add all compatible devices (equivalent to session->add_all())
session = pysmu.Session(add_all=True)

# Grab the first device (equivalent to *(session->m_devices.begin()))
if not session.devices:
    print("No ADALM1000 device found!")
    exit(1)
dev = session.devices[0]

# Fetch the device sample rate so we can convert sample counts to seconds.
sample_rate = dev.get_default_rate()  # samples per second

# Configure at default device rate and start continuous mode (equivalent to
# session->configure(dev->get_default_rate()) and session->start(0))
session.configure(sample_rate)
session.start(continuous=True)

# Running state for cross-batch peak detection.
#   last_peak_sample – absolute sample index of the most recent detected peak
#   prev_voltage     – voltage of the very last sample from the previous batch
#                      (needed to check across batch boundaries)
#   sample_count     – total number of samples read so far
last_peak_sample = None
prev_voltage = None
sample_count = 0

print(f"Sample rate: {sample_rate} Hz  |  Min peak height: {MIN_PEAK_HEIGHT} V")
print("Measuring frequency on Channel A voltage …  (Ctrl+C to stop)\n")

try:
    while True:
        # Read 1024 samples at a time.
        samples = dev.get_samples(1024)
        if not samples:
            continue

        # Extract Channel A voltages for this batch.
        a_voltages = [s[0] for s in samples]

        # Build a padded list so that the first and last samples in the batch
        # can also be tested as peaks using the last sample from the previous
        # batch (if available).
        if prev_voltage is not None:
            padded = [prev_voltage] + a_voltages
            offset = sample_count - 1  # absolute index of padded[0]
        else:
            padded = a_voltages
            offset = sample_count

        # Find peaks within the padded voltage list.
        peak_indices_in_padded = find_peaks(padded)

        for pi in peak_indices_in_padded:
            abs_index = offset + pi  # absolute sample index

            if last_peak_sample is not None:
                samples_between = abs_index - last_peak_sample
                if samples_between > 0:
                    period = samples_between / sample_rate  # seconds
                    frequency = 1.0 / period  # Hz
                    peak_voltage = padded[pi]
                    print(
                        f"Peak detected at sample {abs_index}  "
                        f"({samples_between} samples since last peak)  "
                        f"→  T = {period * 1000:.4f} ms  |  F = {frequency:.4f} Hz  "
                        f"|  Peak voltage = {peak_voltage:.4f} V"
                    )

            last_peak_sample = abs_index

        # Advance global sample counter and remember the last voltage.
        sample_count += len(a_voltages)
        prev_voltage = a_voltages[-1]

except KeyboardInterrupt:
    print("\nStopping ADALM1000 frequency measurement.")
    session.stop()
