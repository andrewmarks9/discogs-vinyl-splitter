#!/usr/bin/env python3
"""Validate split outputs: clipping, fades, edges, containment, overlap, coverage.

Usage: python3 validate_split.py --source <rip> --spec spec.json --dir out/
Writes val_<name>.png spectrograms (first/last 4 s per track). Exit 1 on any FAIL.
Deps: numpy, soundfile, scipy, matplotlib
"""
import argparse, json, sys, os
import numpy as np
import soundfile as sf
from scipy.signal import sosfiltfilt, butter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def db(a): return 20*np.log10(np.sqrt(np.mean(a**2)) + 1e-12)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True)
    ap.add_argument('--spec', required=True)
    ap.add_argument('--dir', default='.')
    args = ap.parse_args()
    spec = json.load(open(args.spec))
    fails = []

    items = list(spec['tracks']) + ([spec['runout']] if spec.get('runout') else [])
    bounds = [(t['name'], t['start'], t['end']) for t in items]
    for k in range(len(bounds)-1):
        n1, s1, e1 = bounds[k]; n2, s2, e2 = bounds[k+1]
        if e1 > s2 + 1e-6: fails.append(f"OVERLAP: {n1} ends {e1} > {n2} starts {s2}")
        elif abs(e1 - s2) > 0.01: print(f"note: {n1}->{n2} gap {s2-e1:.2f}s (ok, adjacency only required for runout)")

    for t in items:
        path = os.path.join(args.dir, f"{t['name']}.wav")
        x, sr = sf.read(path)
        mono = x.mean(axis=1) if x.ndim > 1 else x
        dur = len(mono)/sr
        is_ro = 'runout' in spec and t['name'] == spec['runout']['name']
        xi = x.astype(np.int32) if x.dtype == np.int16 else (x*32767).astype(np.int32)
        full = (xi >= 32766) | (xi <= -32767)
        runs, cur = [], 0
        for v in full.ravel():
            if v: cur += 1
            else:
                if cur: runs.append(cur); cur = 0
        if cur: runs.append(cur)
        nclip = len([r for r in runs if r >= 2])
        eL, eR = db(mono[:int(0.05*sr)]), db(mono[-int(0.05*sr):])
        win = int(0.01*sr); n = len(mono)//win
        env = 20*np.log10(np.sqrt(np.mean(mono[:n*win].reshape(n, win)**2, axis=1)) + 1e-12)
        above = np.where(env > -30)[0]
        contain = (len(above) and above[0]*0.01 >= 0.05 and above[-1]*0.01 <= dur-0.05)
        s0 = float(x[0].min()) if x.ndim > 1 else float(x[0])
        tail = mono[-int(0.02*sr)*4:]; fout = db(tail[:int(0.02*sr)]) - db(tail[-int(0.02*sr):])
        ok_in = abs(s0) < 1e-6
        ok_out = fout > 3
        status = []
        if nclip: status.append(f"FAIL clipping({nclip})"); fails.append(f"{t['name']}: {nclip} clip runs")
        if not is_ro:
            if not contain: status.append("FAIL containment"); fails.append(f"{t['name']}: music touches file edge")
            if eL > -35: status.append(f"FAIL edgeL({eL:.0f})"); fails.append(f"{t['name']}: loud head edge")
            if eR > -35: status.append(f"FAIL edgeR({eR:.0f})"); fails.append(f"{t['name']}: loud tail edge")
        if not ok_in: status.append("FAIL fade-in"); fails.append(f"{t['name']}: sample0 != 0")
        if not ok_out: status.append(f"FAIL fade-out({fout:.1f})"); fails.append(f"{t['name']}: no fade-out")
        print(f"{t['name']:38s} {dur:6.1f}s peak={db(x):6.2f}dB clip={nclip} "
              f"edges={eL:.0f}/{eR:.0f}dB fade_in={'y' if ok_in else 'N'} fade_out={'y' if ok_out else 'N'} "
              f"{' '.join(status) or 'PASS'}")

        if not is_ro:
            fig, axs = plt.subplots(2, 1, figsize=(10, 5))
            for ax, (a, b, ttl) in zip(axs, [(0, 4, f'{t["name"]} - FIRST 4s'), (max(0, dur-4), dur, f'{t["name"]} - LAST 4s')]):
                ax.specgram(mono[int(a*sr):int(b*sr)], NFFT=2048, Fs=sr, noverlap=1024, vmin=-95, vmax=-10, cmap='magma')
                ax.set_title(ttl, fontsize=9); ax.set_ylim(0, 20000)
            fig.tight_layout(); fig.savefig(os.path.join(args.dir, 'val_' + t['name'].split()[0] + '.png'), dpi=90); plt.close(fig)

    # source coverage: no music-band-active window may fall outside all extracted ranges
    x, sr = sf.read(args.source, dtype='float32')
    mono = x.mean(axis=1) if x.ndim > 1 else x
    sos = butter(4, [200, 4000], 'bandpass', fs=sr, output='sos')
    mb = sosfiltfilt(sos, mono)
    w2 = int(0.5*sr); n2 = len(mb)//w2
    me = 20*np.log10(np.sqrt(np.mean(mb[:n2*w2].reshape(n2, w2)**2, axis=1)) + 1e-12)
    mact = me > (np.percentile(me, 10) + 0.35*(np.percentile(me, 90) - np.percentile(me, 10)))
    outside = np.ones(n2, bool)
    for name, s, e in bounds: outside[int(s*2):int(e*2)] = False
    active_out = mact & outside
    missed, i = [], 0   # only SUSTAINED (>=2s) activity outside ranges is a missed song; isolated blips are transients
    while i < n2:
        if active_out[i]:
            j = i
            while j < n2 and active_out[j]: j += 1
            if (j-i)*0.5 >= 2.0: missed.append((i*0.5, j*0.5))
            i = j
        else: i += 1
    if missed: fails.append(f"coverage: sustained music outside extracted ranges: {missed}")
    print(f"source coverage: {len(missed)} sustained music runs outside extracted ranges -> {'PASS' if len(missed)==0 else 'FAIL'}")

    print("RESULT:", "PASS — all gates green" if not fails else f"FAIL — {len(fails)} issue(s)")
    sys.exit(1 if fails else 0)

if __name__ == '__main__':
    main()
