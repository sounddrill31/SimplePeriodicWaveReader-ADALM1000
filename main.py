#!/usr/bin/env python
import sys
import numpy as np
import matplotlib.pyplot as plt
from pysmu import Session, Mode

# --- Configuration ---
SAMPLE_RATE = 100000 
V_PP_THRESHOLD = 0.05  # Lower threshold (50mV)
SNR_THRESHOLD = 8.0    # Lower SNR for easier detection
NUM_SAMPLES = 4096    # 40.96ms buffer
START_BIN = 2         # ~50Hz lower limit

# --- State Management ---
channel_status = {
    'A': {'done': True, 'vpp': 0, 'snr': 0},  # Start A as done but track stats
    'B': {'done': False, 'vpp': 0, 'snr': 0}
}

def interpolate_peak(mag, idx, freqs):
    """
    Parabolic interpolation of the FFT peak.
    Returns (refined_freq, refined_mag)
    """
    if idx <= 0 or idx >= len(mag) - 1:
        return freqs[idx], mag[idx]
    
    y0, y1, y2 = mag[idx-1], mag[idx], mag[idx+1]
    
    # Avoid division by zero
    denom = (y0 - 2*y1 + y2)
    if abs(denom) < 1e-12:
        return freqs[idx], y1
        
    # Delta (offset from idx in bins)
    delta = 0.5 * (y0 - y2) / denom
    
    refined_freq = (idx + delta) * (SAMPLE_RATE / (2 * (len(mag) - 1)))
    refined_mag = y1 - 0.25 * (y0 - y2) * delta
    
    return refined_freq, refined_mag

def get_harmonic_info(magnitude, freq_bins, fundamental_freq):
    harmonics = {}
    f0 = fundamental_freq
    df = freq_bins[1] - freq_bins[0]
    
    # Adaptive search window (around 2 bins or more)
    search_width = max(2, int(0.1 * f0 / df)) if f0 > 0 else 2
    search_width = min(search_width, 15)
    
    for n in range(1, 7): # Check up to 6 harmonics
        target_f = n * f0
        if target_f > (SAMPLE_RATE / 2) - 100: break
        
        idx = np.argmin(np.abs(freq_bins - target_f))
        start, end = max(0, idx - search_width), min(len(magnitude), idx + search_width + 1)
        
        # Within window, find the actual peak for the harmonic
        h_idx = np.argmax(magnitude[start:end]) + start
        h_freq, h_mag = interpolate_peak(magnitude, h_idx, freq_bins)
        
        harmonics[n] = {'freq': h_freq, 'mag': h_mag}
        
    return harmonics

def get_wave_type_advanced(voltages, harmonics):
    v_max, v_min = np.max(voltages), np.min(voltages)
    v_pp = v_max - v_min
    v_rms = np.sqrt(np.mean((voltages - np.mean(voltages))**2))
    
    if not harmonics or 1 not in harmonics:
        return "Unknown"
        
    m1 = harmonics[1]['mag']
    m2 = harmonics.get(2, {'mag': 0})['mag'] / m1
    m3 = harmonics.get(3, {'mag': 0})['mag'] / m1
    m5 = harmonics.get(5, {'mag': 0})['mag'] / m1
    
    # --- FFT-based Decision ---
    # Sine: Very low harmonics
    if m2 < 0.1 and m3 < 0.1:
        return "Sine"
        
    # Square: Strong odd (m3 ~ 0.33), low even
    if m2 < 0.15 and m3 > 0.2:
        return "Square"
        
    # Triangle: Weak odd (m3 ~ 0.11), very low even
    if m2 < 0.1 and m3 > 0.05 and m3 < 0.2:
        return "Triangle"
        
    # Fallback: Time Domain Shape Factors (Best fit among the three)
    sine_err = abs(v_rms - v_pp / (2 * np.sqrt(2)))
    square_err = abs(v_rms - v_pp / 2)
    triangle_err = abs(v_rms - v_pp / np.sqrt(12))
    
    errors = {'Sine': sine_err, 'Square': square_err, 'Triangle': triangle_err}
    return min(errors, key=errors.get)

def check_periodicity_fft(voltages):
    v_max, v_min = np.max(voltages), np.min(voltages)
    v_pp = v_max - v_min
    
    # Remove DC
    v_centered = voltages - np.mean(voltages)
    
    # Hanning window and FFT
    window = np.hanning(len(v_centered))
    xf = np.fft.rfft(v_centered * window)
    
    # Magnitude scaling for Hanning window (coherent gain correction)
    # * 2.0 (for rfft positive bins) * 2.0 (for Hann gain compensation) / len(voltages)
    magnitude = np.abs(xf) * 4.0 / len(voltages)
    freq_bins = np.fft.rfftfreq(len(voltages), 1/SAMPLE_RATE)
    
    # Peak search
    search_mag = magnitude[START_BIN:]
    if len(search_mag) == 0:
        return None, v_pp, magnitude, freq_bins
        
    peak_idx = np.argmax(search_mag) + START_BIN
    noise_floor = np.median(magnitude[START_BIN:])
    snr = magnitude[peak_idx] / (noise_floor + 1e-9)
    
    if snr > SNR_THRESHOLD and v_pp > V_PP_THRESHOLD:
        refined_f, _ = interpolate_peak(magnitude, peak_idx, freq_bins)
        return refined_f, v_pp, magnitude, freq_bins
        
    return None, v_pp, magnitude, freq_bins

def plot_waveform_fft(chan_name, voltages, freq, wave_type, magnitude, freq_bins, harmonics):
    time = np.arange(len(voltages)) / SAMPLE_RATE * 1000 
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    
    # Time Domain
    ax1.plot(time, voltages, color='tab:blue')
    ax1.set_title(f"Waveform Analysis: Channel {chan_name} ({wave_type})")
    ax1.set_xlabel("Time (ms)")
    ax1.set_ylabel("Voltage (V)")
    ax1.grid(True, alpha=0.3)
    
    v_pp, v_avg = np.max(voltages) - np.min(voltages), np.mean(voltages)
    ax1.annotate(f"Freq: {freq:.2f} Hz\nVpp: {v_pp:.3f} V\nAvg: {v_avg:.3f} V", 
                 xy=(0.02, 0.95), xycoords='axes fraction', 
                 bbox=dict(boxstyle="round", fc="w", alpha=0.5), verticalalignment='top')

    # Freq Domain
    show_limit = len(freq_bins) // 4
    ax2.plot(freq_bins[:show_limit], magnitude[:show_limit], color='tab:red', alpha=0.4)
    ax2.set_title("Frequency Spectrum (Interpolated)")
    ax2.set_xlabel("Frequency (Hz)")
    ax2.set_ylabel("Magnitude (V)")
    ax2.grid(True, alpha=0.3)
    
    for n, data in harmonics.items():
        if data['freq'] < freq_bins[show_limit]:
            ax2.plot(data['freq'], data['mag'], "x", color='black')
            ax2.annotate(f"{n}f", xy=(data['freq'], data['mag']), 
                         xytext=(2, 2), textcoords='offset points', fontsize=8)
    
    plt.tight_layout()
    plt.show()

def main():
    session = Session()
    if not session.devices:
        print("No devices attached")
        sys.exit(1)

    dev = session.devices[0]
    dev.channels['A'].mode = Mode.HI_Z
    dev.channels['B'].mode = Mode.HI_Z
    session.start(0)

    print("\nScanning for periodic waves...")
    print("Press Ctrl+C to terminate.\n")

    try:
        while True:
            samples = dev.read(NUM_SAMPLES)
            if not samples: continue
            
            # Update stats and check periodicity
            v_a = np.array([s[0][0] for s in samples])
            v_b = np.array([s[1][0] for s in samples])
            
            signals = {'A': v_a, 'B': v_b}
            
            for chan in ['A', 'B']:
                voltages = signals[chan]
                f_locked, vpp, magnitude, freqs = check_periodicity_fft(voltages)
                
                # Live tracking safety checks
                if magnitude is not None and len(magnitude) > START_BIN:
                    mag_slice = magnitude[START_BIN:]
                    noise = np.median(mag_slice)
                    max_mag = np.max(mag_slice)
                    snr = max_mag / (noise + 1e-9)
                else:
                    snr = 0
                
                channel_status[chan]['vpp'] = vpp
                channel_status[chan]['snr'] = snr
                
                # Reset "done" if signal is gone (lower than threshold)
                if vpp < (V_PP_THRESHOLD / 2):
                    channel_status[chan]['done'] = False
                
                # Focus Prompt
                if f_locked and not channel_status[chan]['done']:
                    print(f"\n\n>>> LOCK! {f_locked:.1f}Hz @ Channel {chan} (SNR: {snr:.1f}, Vpp: {vpp:.3f}V)")
                    try:
                        ans = input(f"Focus on Channel {chan}? [y/N]: ").strip().lower()
                    except EOFError: ans = 'n'
                    
                    if ans == 'y':
                        harmonics = get_harmonic_info(magnitude, freqs, f_locked)
                        wave_type = get_wave_type_advanced(voltages, harmonics)
                        print("-" * 30)
                        print(f"Type: {wave_type} | Harmonics (ratio to f1):")
                        for n in range(2, 6):
                            if n in harmonics:
                                print(f"  {n}f: {harmonics[n]['mag']/harmonics[1]['mag']:.1%}", end=" ")
                        print("\n" + "-" * 30)
                        plot_waveform_fft(chan, voltages, f_locked, wave_type, magnitude, freqs, harmonics)
                    
                    channel_status[chan]['done'] = True
                    print("\nScanning...")

            # Live Status Output
            status = f"A: {channel_status['A']['vpp']:.3f}V (SNR:{channel_status['A']['snr']:4.1f}) | " \
                     f"B: {channel_status['B']['vpp']:.3f}V (SNR:{channel_status['B']['snr']:4.1f}) "
            sys.stdout.write("\r" + status)
            sys.stdout.flush()

    except KeyboardInterrupt:
        print("\n\nTerminated.")
    finally:
        try: session.end()
        except: pass

if __name__ == "__main__":
    main()
