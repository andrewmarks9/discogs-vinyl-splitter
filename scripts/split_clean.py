#!/usr/bin/env python3
"""Split a vinyl rip per spec JSON, decrackle + denoise tracks, save runout raw.

Usage: python3 split_clean.py --source <rip> --spec spec.json --outdir out/
Spec: {"source": "...", "tracks": [{"name": "A1 Title", "start": 10.36, "end": 168.40}],
       "runout": {"name": "Side B Runout", "start": 312.35, "end": 322.0}}
Deps: numpy, soundfile, scipy, ffmpeg on PATH
"""
import argparse, json, subprocess, os
import numpy as np
import soundfile as sf
from scipy.ndimage import median_filter

def decrackle(seg, sr):
    out, nrep = seg.copy(), 0
    w = int(0.025 * sr)
    for ch in range(seg.shape[1]):
        s = out[:, ch].astype(np.float64)
        med = median_filter(s, size=9, mode='nearest')
        r = s - med
        cs = np.cumsum(r*r); loc = np.sqrt((cs - np.concatenate([np.zeros(w), cs[:-w]]))/w) + 1e-9
        cs2 = np.cumsum(s*s); lsig = np.sqrt((cs2 - np.concatenate([np.zeros(w), cs2[:-w]]))/w) + 1e-9
        m = np.abs(r) > np.maximum.reduce([8*loc, 0.3*lsig, np.full(len(s), 0.04)])
        events = []
        for i in np.where(m)[0]:
            if events and i - events[-1][-1] <= 3: events[-1].append(i)
            else: events.append([i])
        keep = [e for e in events if e[-1]-e[0] <= int(0.003*sr)]
        for ev in keep:
            a0, a1 = max(1, ev[0]-4), min(len(s)-1, ev[-1]+5)
            out[a0:a1, ch] = np.interp(np.arange(a0, a1), [a0-1, a1], [s[a0-1], s[a1]]).astype(np.float32)
        nrep += len(keep)
    return out, nrep

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True)
    ap.add_argument('--spec', required=True)
    ap.add_argument('--outdir', default='.')
    args = ap.parse_args()
    spec = json.load(open(args.spec))
    os.makedirs(args.outdir, exist_ok=True)
    x, sr = sf.read(args.source, dtype='float32')

    for t in spec['tracks']:
        seg = x[int(t['start']*sr):int(t['end']*sr)]
        seg, nrep = decrackle(seg, sr)
        tmp = os.path.join(args.outdir, 'tmp_float.wav')
        sf.write(tmp, seg, sr, subtype='FLOAT')
        dur = len(seg)/sr
        final = os.path.join(args.outdir, f"{t['name']}.wav")
        af = (f"highpass=f=32,lowpass=f=13000,afftdn=nr=15:nf=-45:tn=1,"
              f"afade=t=in:st=0:d=0.015,afade=t=out:st={dur-0.15:.3f}:d=0.15")
        assert subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp,
                               "-af", af, "-c:a", "pcm_s16le", final]).returncode == 0
        os.remove(tmp)
        print(f"track: {t['name']}.wav  {dur:.2f}s  click repairs: {nrep}  peak(pre-clean)={np.abs(seg).max():.3f}")

    ro = spec.get('runout')
    if ro:
        seg = x[int(ro['start']*sr):int(ro['end']*sr)].copy()
        seg[:int(0.015*sr)] *= np.linspace(0, 1, int(0.015*sr))[:, None]
        seg[-int(0.15*sr):] *= np.linspace(1, 0, int(0.15*sr))[:, None]
        final = os.path.join(args.outdir, f"{ro['name']}.wav")
        sf.write(final, seg, sr, subtype='PCM_16')
        print(f"runout: {ro['name']}.wav  {len(seg)/sr:.2f}s  (RAW — fades only, no denoise)")

if __name__ == '__main__':
    main()
