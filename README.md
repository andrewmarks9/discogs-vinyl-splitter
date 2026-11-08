# README — discogs-vinyl-splitter

Split a captured vinyl side into tracks using a Discogs release as ground truth.
Detects real song boundaries in the audio (rumble-immune), removes turntable noise,
keeps runout as a separate raw file, and validates every split before delivering.

## Trigger phrases

The skill activates when a message contains **both** a Discogs release URL
(`discogs.com/release/...`) **and** an attached vinyl rip (`.WAV` / `.wav` / `.flac`
side file). **That alone is enough — no instruction words required.** The URL plus the
attachment *is* the split request; the agent starts the split immediately with default
settings (tight trims, full noise removal, runout kept raw). Explicit phrasings also
work and are only needed to add options:

- `https://www.discogs.com/release/14390598-…` + [kalfonsidea.WAV attached] ← zero
  extra words needed
- "Split Side A based on https://www.discogs.com/release/14390598-… — trim silence
  tightly, remove turntable noise, and validate the splits."
- "Here's the rip: sideb.WAV — split into tracks per
  https://www.discogs.com/release/12345-…, keep the runout as a separate file."
- "Use discogs-vinyl-splitter on this side, Discogs URL: <url>"

A URL with no rip attached, or a rip with no URL, is not a trigger — the agent asks
for the missing piece instead of guessing.

## Pointing it at a new release and rip

1. **Attach the side rip** to your message — one side per file (Side A and Side B are
   separate jobs).
2. **Paste the Discogs release URL** for that exact pressing (track counts differ
   between pressings).
3. **Say which side** the file is (A or B — or the agent infers it from the tracklist
   vs measured duration).
4. Optional requests:
   - *Runout*: default is keep as a separate **raw** file (fades only, no denoise).
     Say "discard the runout" to skip it.
   - *Format*: default output is WAV, source sample rate, 16-bit stereo.
5. The agent runs the whole flow: fetch tracklist → detect boundaries → split →
   decrackle/denoise → validate (clipping, fades, edges, overlap, coverage) →
   deliver files + validation spectrograms. It can also archive to your AI Drive in a
   folder named `<Artist> - <Title> (split WAV)` — just ask.

## Manual CLI usage

```bash
# 1. Structure analysis (tells you where every song, gap, and blip is)
python3 scripts/analyze_structure.py <side-rip.WAV>

# 2. Write a spec JSON from the analysis
cat > spec.json << 'EOF'
{"source": "/path/to/side-rip.WAV",
 "tracks": [
   {"name": "A1 First Song",  "start": 10.36, "end": 168.40},
   {"name": "A2 Second Song", "start": 170.96, "end": 286.95}
 ],
 "runout": {"name": "Side A Runout", "start": 286.95, "end": 290.5}}
EOF

# 3. Split + clean (decrackle, 32 Hz rumble filter, 13 kHz hiss filter, FFT denoise, fades)
python3 scripts/split_clean.py --source /path/to/side-rip.WAV --spec spec.json --outdir out/

# 4. Validate (exit 1 on any failure; writes val_*.png spectrograms)
python3 scripts/validate_split.py --source /path/to/side-rip.WAV --spec spec.json --dir out/
```

Times in the spec are seconds on the source-file timeline, taken from the analyzer's
sustained music runs (starts) minus 0.2 s pre-roll, and run ends plus 0.55–0.85 s tail
allowance, clamped so files never overlap.

## Validation gates (enforced, non-negotiable)

| Gate | Meaning |
|---|---|
| Clipping | 0 runs ≥ 2 consecutive samples at full scale |
| Fades | sample 0 exactly 0.0; tail RMS falls > 3 dB |
| Edges | first/last 50 ms ≤ −35 dB — no mid-song cuts |
| Containment | all music inside the file, nothing truncated |
| Overlap | every file ends before the next begins; runout adjacency exact |
| Coverage | no sustained music left in the discarded regions |

## Rules baked into the workflow

- **The audio always wins.** Discogs durations are submitter-estimated and often padded
  5–15 s; they sanity-check the split, they never set it.
- One side per file, per job.
- Runout is the artifact — it ships raw (fades only) and separate.
- Any gate FAIL blocks delivery until fixed and re-verified.

## Requirements

Python 3 with `numpy`, `soundfile`, `scipy`, `matplotlib`; `ffmpeg` on PATH.
