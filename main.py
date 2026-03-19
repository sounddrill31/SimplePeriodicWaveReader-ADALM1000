#!/usr/bin/env python
import sys
import numpy as np
import matplotlib.pyplot as plt
from pysmu import Session, Mode
from scipy.signal import find_peaks

# --- Configuration ---
SAMPLE_RATE = 100000 
V_PP_THRESHOLD = 0.1  # Minimum peak-to-peak voltage to consider a signal
CONSISTENCY_THRESHOLD = 0.1  # Relative tolerance for peak spacing consistency
PEAK_DIST_MIN = 5  # Minimum distance between peaks (prevents high frequency noise as peaks)

# --- State Management ---
# channel_states = {'A': 'IDLE', 'B': 'IDLE'}
# 'IDLE': No significant signal
# 'DETECTED': Periodic wave found, waiting to ask user
# 'DONE': User was asked (focused or skipped). Resets if signal disappears.
channel_status = {
    'A': {'state': 'IDLE', 'done': True},  # Channel A starts as "done" per user request
    'B': {'state': 'IDLE', 'done': False}
}

def get_wave_type(voltages):
    """
    Identifies the wave type based on statistical properties of the waveform.
    """
    v_max = np.max(voltages)
    v_min = np.min(voltages)
    v_pp = v_max - v_min
    v_avg = np.mean(voltages)
    v_centered = voltages - v_avg
    v_rms = np.sqrt(np.mean(v_centered**2))
    
    # Shape Factor / RMS comparison
    # Sine: Vpp / (2 * sqrt(2)) approx V_rms
    # Square: Vpp / 2 approx V_rms
    # Triangle: Vpp / sqrt(12) approx V_rms
    
    sine_err = abs(v_rms - v_pp / (2 * np.sqrt(2)))
    square_err = abs(v_rms - v_pp / 2)
    triangle_err = abs(v_rms - v_pp / np.sqrt(12))
    
    errors = {'Sine': sine_err, 'Square': square_err, 'Triangle': triangle_err}
    best_fit = min(errors, key=errors.get)
    
    # Refine Square Wave: check if it spends most time at peaks
    if best_fit == 'Square':
        # Probability density near peaks
        margin = 0.1 * v_pp
        near_peaks = np.sum((voltages > v_max - margin) | (voltages < v_min + margin))
        if near_peaks / len(voltages) < 0.6: # If it's not staying at peaks, maybe it's something else
            best_fit = 'Complex/Periodic'
            
    return best_fit

def check_periodicity(voltages):
    """
    Checks if the signal is periodic and returns frequency and peaks if it is.
    """
    v_max = np.max(voltages)
    v_min = np.min(voltages)
    v_pp = v_max - v_min
    
    if v_pp < V_PP_THRESHOLD:
        return None, v_pp, None
    
    # Use find_peaks on centered and normalized signal
    v_avg = np.mean(voltages)
    v_centered = voltages - v_avg
    
    # Look for peaks on the positive side
    peaks, _ = find_peaks(v_centered, height=v_pp*0.25, distance=PEAK_DIST_MIN)
    
    if len(peaks) < 3:
        return None, v_pp, None
    
    # Check consistency of peak distances
    diffs = np.diff(peaks)
    avg_diff = np.mean(diffs)
    std_diff = np.std(diffs)
    
    if std_diff / avg_diff < CONSISTENCY_THRESHOLD:
        freq = SAMPLE_RATE / avg_diff
        return freq, v_pp, peaks
    
    return None, v_pp, None

def plot_waveform(chan_name, voltages, freq, wave_type, peaks):
    """
    Pop up a matplotlib window with the waveform.
    """
    time = np.arange(len(voltages)) / SAMPLE_RATE * 1000 # Time in ms
    
    plt.figure(figsize=(10, 5))
    plt.plot(time, voltages, label=f'Ch {chan_name} Signal', color='tab:blue')
    
    if peaks is not None:
        plt.plot(time[peaks], voltages[peaks], "x", label='Detected Peaks', color='tab:red')
        
    plt.title(f"Waveform Analysis: Channel {chan_name} ({wave_type})")
    plt.xlabel("Time (ms)")
    plt.ylabel("Voltage (V)")
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Text info on plot
    v_pp = np.max(voltages) - np.min(voltages)
    v_avg = np.mean(voltages)
    info_text = f"Freq: {freq:.2f} Hz\nVpp: {v_pp:.3f} V\nAvg: {v_avg:.3f} V"
    plt.annotate(info_text, xy=(0.02, 0.95), xycoords='axes fraction', 
                 bbox=dict(boxstyle="round", fc="w", alpha=0.5), verticalalignment='top')
    
    plt.legend(loc='upper right')
    plt.tight_layout()
    print("Showing plot... (Close the window to continue)")
    plt.show()

def focus_analysis(chan_name, voltages, freq, peaks):
    v_max = np.max(voltages)
    v_min = np.min(voltages)
    v_pp = v_max - v_min
    v_avg = np.mean(voltages)
    wave_type = get_wave_type(voltages)
    
    print("\n" + "="*40)
    print(f"FOCUS ANALYSIS: CHANNEL {chan_name}")
    print(f"Wave Type:   {wave_type}")
    print(f"Frequency:   {freq:.2f} Hz")
    print(f"Peak-to-Peak: {v_pp:.3f} V")
    print(f"Average:     {v_avg:.3f} V")
    print(f"Max / Min:   {v_max:.3f} V / {v_min:.3f} V")
    print("="*40 + "\n")
    
    plot_waveform(chan_name, voltages, freq, wave_type, peaks)

def main():
    session = Session()

    if not session.devices:
        print("No devices attached")
        sys.exit(1)

    dev = session.devices[0]
    # Set to High Impedance to just measure if sourcing isn't needed
    # But user's script used SVMI, let's stick to it or HI_Z for measurement
    dev.channels['A'].mode = Mode.HI_Z
    dev.channels['B'].mode = Mode.HI_Z

    session.start(0)

    num_samples = 4096 # Larger buffer for better analysis
    
    print("Scanning for periodic waves...")
    print(f"(Channel A is {'DONE' if channel_status['A']['done'] else 'ENABLED'})")
    print("Press Ctrl+C to terminate.")

    try:
        while True:
            samples = dev.read(num_samples)
            if not samples:
                continue

            # data[chan][val/cur]
            v_a = np.array([s[0][0] for s in samples])
            v_b = np.array([s[1][0] for s in samples])
            
            signals = {'A': v_a, 'B': v_b}
            
            for chan in ['A', 'B']:
                voltages = signals[chan]
                freq, v_pp, peaks = check_periodicity(voltages)
                
                # Update "removed" status: if signal disappears, reset 'done'
                if v_pp < V_PP_THRESHOLD:
                    if channel_status[chan]['done']:
                        # print(f"Signal removed from Channel {chan}. Scanning re-enabled.")
                        channel_status[chan]['done'] = False
                    continue

                # If periodic wave detected and not done
                if freq and not channel_status[chan]['done']:
                    # Detected! Ask user
                    print(f"\n>>> Periodic wave ({freq:.1f} Hz) detected on Channel {chan}!")
                    try:
                        ans = input(f"Focus on Channel {chan}? [y/N]: ").strip().lower()
                    except EOFError:
                        ans = 'n'
                    
                    if ans == 'y':
                        focus_analysis(chan, voltages, freq, peaks)
                    
                    channel_status[chan]['done'] = True
                    print("Resuming scan...")

    except KeyboardInterrupt:
        print("\nTerminated.")
    finally:
        try:
            session.end()
        except:
            pass

if __name__ == "__main__":
    main()
