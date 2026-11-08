#!/usr/bin/env python3
"""Structure analyzer for vinyl-rip splitting. Prints everything needed to pick split points.

Usage: python3 analyze_structure.py <audiofile>
Deps: numpy, soundfile, scipy
"""
import sys
import numpy as np
import soundfile as sf
from scipy.signal import sosfiltfilt, butter, welch

def main():
    path = sys.argv[1]
    x, sr = sf.read(path, dtype='float32')
    mono = x.mean(axis=1) if x.ndim > 1 else x
    dur = len(mono) / sr
    print(f"file: {path}")
    print(f"format: {sr} Hz, {x.ndim} ch, {dur:.2f}s ({int(dur//60)}:{dur%60:04.1f})")
    print(f"peak: {np.abs(x).max():.6f}  DC: L={x[:,0].mean():.6f} R={x[:,1].mean():.6f}" if x.ndim > 1
          else f"peak: {np.abs(x).max():.6f}  mono")

    # full-band envelope (20 ms) for quiet regions
    win = int(0.02 * sr)
    nw = len(mono) // win
    env = 20*np.log10(np.sqrt(np.mean(mono[:nw*win].reshape(nw, win)**2, axis=1)) + 1e-12)
    floor = np.percentile(env, 10)
    print(f"\n[full-band] floor={floor:.1f} dB  p90={np.percentile(env,90):.1f} dB")
    quiet = env < floor + 12
    regs, i = [], 0
    while i < nw:
        if quiet[i]:
            j = i
            while j < nw and quiet[j]: j += 1
            if (j-i)*0.02 >= 0.25: regs.append((i*0.02, j*0.02, (j-i)*0.02, env[i:j].min()))
            i = j
        else: i += 1
    print("quiet regions >=0.25s (start, end, len, min dB):")
    for s, e, l, mn in regs: print(f"  {s:8.2f} -> {e:8.2f}  len={l:6.2f}s  min={mn:6.1f}")

    # music-band envelope (0.5 s) — rumble-immune structure detection
    sos = butter(4, [200, 4000], 'bandpass', fs=sr, output='sos')
    mb = sosfiltfilt(sos, mono)
    w2 = int(0.5 * sr); n2 = len(mb) // w2
    me = 20*np.log10(np.sqrt(np.mean(mb[:n2*w2].reshape(n2, w2)**2, axis=1)) + 1e-12)
    mp10, mp90 = np.percentile(me, 10), np.percentile(me, 90)
    mact = me > (mp10 + 0.35 * (mp90 - mp10))
    print(f"\n[music-band 200-4k] p10={mp10:.1f} p90={mp90:.1f} thr={mp10 + 0.35*(mp90-mp10):.1f} dB")
    runs, i = [], 0
    while i < n2:
        if mact[i]:
            j = i
            while j < n2 and mact[j]: j += 1
            if (j-i)*0.5 >= 2.0: runs.append((i*0.5, j*0.5))
            i = j
        else: i += 1
    print("sustained music runs >=2s (= candidate songs):")
    for a, b in runs: print(f"  {a:8.1f} -> {b:8.1f}  len={b-a:6.1f}s")
    if len(runs) >= 2:
        gaps = [(runs[k][1], runs[k+1][0], runs[k+1][0]-runs[k][1]) for k in range(len(runs)-1)]
        print("inter-track gaps between runs:", [(round(a,1), round(b,1), round(l,1)) for a, b, l in gaps])
    if runs:
        e2 = runs[-1][1]
        blips, j = [], int(e2*2)
        while j < n2:
            if mact[j]:
                k = j
                while k < n2 and mact[k]: k += 1
                seg = mono[j*w2:k*w2]
                f, p = welch(seg, sr, nperseg=4096)
                tot = 20*np.log10(np.sqrt(np.mean(seg**2)) + 1e-12)
                hf = f > 1000
                blips.append((j*0.5, (k-j)*0.5, f[np.argmax(p)], tot,
                              100*np.trapezoid(p[hf], f[hf])/np.trapezoid(p, f)))
                j = k
            else: j += 1
        if blips:
            print("post-music blips (t, len, dominant-freq, RMS, >1kHz%) — runout candidates if thump-like:")
            for b in blips: print(f"  t={b[0]:7.1f}s len={b[1]:4.1f}s dom={b[2]:6.0f}Hz rms={b[3]:6.1f}dB hf%={b[4]:4.0f}")
        tail = me[int(e2*2):]
        print(f"post-music tail max music-band level: {tail.max():.1f} dB "
              f"({'digital silence after blips' if tail.max() < -75 else 'audible content — inspect'})")

    print("\n[coarse 2s-bin full-band envelope]")
    line = []
    for k in range(0, int(dur), 2):
        a, b = int(k*sr/win), min(int((k+2)*sr/win), nw)
        if a < nw: line.append(f"{k}s:{env[a:b].mean():.0f}")
    for k in range(0, len(line), 8): print("  " + " ".join(line[k:k+8]))

if __name__ == '__main__':
    main()
