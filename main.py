#!/usr/bin/env python
import sys
import numpy as np
import matplotlib.pyplot as plt
from pysmu import Session, Mode

# --- Configuration ---
SAMPLE_RATE = 100000 
V_PP_THRESHOLD = 0.1  # Minimum peak-to-peak voltage to consider a signal
SNR_THRESHOLD = 15.0  # Magnitude of fundamental vs median noise (in linear scale)
NUM_SAMPLES = 4096    # 40.96ms @ 100kSPS (Freq resolution ~24.4 Hz)

# --- State Management ---
channel_status = {
    'A': {'done': True},  # Channel A starts as "done" per user request
    'B': {'done': False}
}

def get_harmonic_info(magnitude, freq_bins, fundamental_freq):
    """
    Extracts magnitudes of the first 5 harmonics.
    """
    harmonics = {}
    f0 = fundamental_freq
    df = freq_bins[1] - freq_bins[0]
    search_width = int(2.5 / (df / f0)) if f0 > 0 else 5 # Search within a few bins
    search_width = max(2, min(search_width, 10))
    
    for n in range(1, 6):
        target_freq = n * f0
        if target_freq > SAMPLE_RATE / 2:
            break
            
        # Find index closest to n * f0
        idx = np.argmin(np.abs(freq_bins - target_freq))
        
        # Search window for peak
        start = max(0, idx - search_width)
        end = min(len(magnitude), idx + search_width + 1)
        
        peak_mag = np.max(magnitude[start:end])
        harmonics[n] = {'freq': target_freq, 'mag': peak_mag}
        
    return harmonics

def get_wave_type_advanced(voltages, harmonics):
    """
    Identifies wave type using both time-domain and harmonic ratios.
    """
    v_max, v_min = np.max(voltages), np.min(voltages)
    v_pp = v_max - v_min
    v_rms = np.sqrt(np.mean((voltages - np.mean(voltages))**2))
    
    if not harmonics or 1 not in harmonics:
        return "Unknown"
        
    m1 = harmonics[1]['mag']
    m2 = harmonics.get(2, {'mag': 0})['mag'] / m1
    m3 = harmonics.get(3, {'mag': 0})['mag'] / m1
    m5 = harmonics.get(5, {'mag': 0})['mag'] / m1
    
    # 1. Sine check: Low harmonics
    if m2 < 0.1 and m3 < 0.1:
        return "Sine"
        
    # 2. Square check: Strong odd harmonics (m3 ~ 0.33, m5 ~ 0.2), low even
    if m2 < 0.15 and m3 > 0.2 and m3 < 0.5:
        return "Square"
        
    # 3. Triangle check: Weak odd harmonics (m3 ~ 0.11, m5 ~ 0.04), low even
    if m2 < 0.1 and m3 > 0.05 and m3 < 0.15:
        return "Triangle"
        
    # 4. Sawtooth check: Strong even and odd harmonics (m2 ~ 0.5, m3 ~ 0.33)
    if m2 > 0.3 and m3 > 0.2:
        return "Sawtooth"
        
    # Fallback to RMS-based if FFT is ambiguous
    sine_err = abs(v_rms - v_pp / (2 * np.sqrt(2)))
    square_err = abs(v_rms - v_pp / 2)
    triangle_err = abs(v_rms - v_pp / np.sqrt(12))
    
    errors = {'Sine': sine_err, 'Square': square_err, 'Triangle': triangle_err}
    return min(errors, key=errors.get)

def check_periodicity_fft(voltages):
    v_max, v_min = np.max(voltages), np.min(voltages)
    v_pp = v_max - v_min
    
    if v_pp < V_PP_THRESHOLD:
        return None, v_pp, None, None
    
    v_centered = voltages - np.mean(voltages)
    window = np.hanning(len(v_centered))
    v_windowed = v_centered * window
    
    xf = np.fft.rfft(v_windowed)
    magnitude = np.abs(xf) * 2.0 / len(voltages)
    freq_bins = np.fft.rfftfreq(len(voltages), 1/SAMPLE_RATE)
    
    start_idx = 4 
    search_mag = magnitude[start_idx:]
    search_freqs = freq_bins[start_idx:]
    
    if len(search_mag) == 0:
        return None, v_pp, None, None
        
    peak_idx = np.argmax(search_mag)
    fundamental_mag = search_mag[peak_idx]
    fundamental_freq = search_freqs[peak_idx]
    
    noise_floor = np.median(magnitude[start_idx:])
    snr = fundamental_mag / (noise_floor + 1e-6)
    
    if snr > SNR_THRESHOLD:
        return fundamental_freq, v_pp, magnitude, freq_bins
        
    return None, v_pp, magnitude, freq_bins

def plot_waveform_fft(chan_name, voltages, freq, wave_type, magnitude, freq_bins, harmonics):
    time = np.arange(len(voltages)) / SAMPLE_RATE * 1000 
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    
    # --- Time Domain ---
    ax1.plot(time, voltages, label=f'Ch {chan_name} Signal', color='tab:blue')
    ax1.set_title(f"Waveform Analysis: Channel {chan_name} ({wave_type})")
    ax1.set_xlabel("Time (ms)")
    ax1.set_ylabel("Voltage (V)")
    ax1.grid(True, linestyle='--', alpha=0.7)
    
    v_pp = np.max(voltages) - np.min(voltages)
    v_avg = np.mean(voltages)
    info_text = f"Freq: {freq:.2f} Hz\nVpp: {v_pp:.3f} V\nAvg: {v_avg:.3f} V"
    ax1.annotate(info_text, xy=(0.02, 0.95), xycoords='axes fraction', 
                 bbox=dict(boxstyle="round", fc="w", alpha=0.5), verticalalignment='top')
    ax1.legend(loc='upper right')

    # --- Frequency Domain ---
    show_limit = len(freq_bins) // 4
    ax2.plot(freq_bins[:show_limit], magnitude[:show_limit], color='tab:red', alpha=0.5)
    ax2.set_title("Harmonic Spectrum (FFT)")
    ax2.set_xlabel("Frequency (Hz)")
    ax2.set_ylabel("Magnitude (V)")
    ax2.grid(True, linestyle='--', alpha=0.7)
    
    # Highlight harmonics
    for n, data in harmonics.items():
        if data['freq'] < freq_bins[show_limit]:
            ax2.plot(data['freq'], data['mag'], "x", color='black')
            ax2.annotate(f"{n}f", xy=(data['freq'], data['mag']), 
                         xytext=(3, 3), textcoords='offset points', fontsize=9)
    
    plt.tight_layout()
    print("Showing plot... (Close the window to continue)")
    plt.show()

def focus_analysis(chan_name, voltages, freq, magnitude, freq_bins):
    harmonics = get_harmonic_info(magnitude, freq_bins, freq)
    wave_type = get_wave_type_advanced(voltages, harmonics)
    v_max, v_min = np.max(voltages), np.min(voltages)
    v_pp, v_avg = v_max - v_min, np.mean(voltages)
    
    print("\n" + "="*40)
    print(f"FOCUS ANALYSIS: CHANNEL {chan_name}")
    print(f"Wave Type:   {wave_type}")
    print(f"Frequency:   {freq:.2f} Hz")
    print(f"Peak-to-Peak: {v_pp:.3f} V")
    print(f"Average:     {v_avg:.3f} V")
    print("-" * 20)
    print("Harmonic Profile (Ratio to Fundamental):")
    for n in range(1, 6):
        if n in harmonics:
            ratio = harmonics[n]['mag'] / harmonics[1]['mag']
            print(f"  {n}f ({harmonics[n]['freq']/1000:.2f}kHz): {ratio:.2%}")
    print("="*40 + "\n")
    
    plot_waveform_fft(chan_name, voltages, freq, wave_type, magnitude, freq_bins, harmonics)

def main():
    session = Session()
    if not session.devices:
        print("No devices attached")
        sys.exit(1)

    dev = session.devices[0]
    dev.channels['A'].mode = Mode.HI_Z
    dev.channels['B'].mode = Mode.HI_Z
    session.start(0)

    print("Scanning for periodic waves (Advanced Harmonic Mode)...")
    print(f"(Channel A is {'DONE' if channel_status['A']['done'] else 'ENABLED'})")
    print("Press Ctrl+C to terminate.")

    try:
        while True:
            samples = dev.read(NUM_SAMPLES)
            if not samples: continue
            v_a = np.array([s[0][0] for s in samples])
            v_b = np.array([s[1][0] for s in samples])
            signals = {'A': v_a, 'B': v_b}
            
            for chan in ['A', 'B']:
                voltages = signals[chan]
                freq, v_pp, magnitude, freq_bins = check_periodicity_fft(voltages)
                
                if v_pp < V_PP_THRESHOLD:
                    if channel_status[chan].get('done'):
                        channel_status[chan]['done'] = False
                    continue

                if freq and not channel_status[chan].get('done'):
                    print(f"\n>>> Periodic wave detected on Channel {chan}!")
                    try:
                        ans = input(f"Focus on Channel {chan}? [y/N]: ").strip().lower()
                    except EOFError: ans = 'n'
                    
                    if ans == 'y':
                        focus_analysis(chan, voltages, freq, magnitude, freq_bins)
                    
                    channel_status[chan]['done'] = True
                    print("Resuming scan...")

    except KeyboardInterrupt:
        print("\nTerminated.")
    finally:
        try: session.end()
        except: pass

if __name__ == "__main__":
    main()
