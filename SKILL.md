---
name: discogs-vinyl-splitter
description: Use when the user gives a Discogs release URL plus a captured vinyl rip (WAV/FLAC side file) and wants it split into tracks — fetches the official Discogs track list, detects song boundaries in the rip (robust to rumble-heavy or noisy recordings), splits at real music boundaries, removes turntable noise (decrackle, rumble/hiss filters, FFT denoise), keeps runout/lead-out as a separate raw file, and validates every split (complete songs, no mid-song cuts, no overlap, no clipping, fades present) before delivering.
---

# Discogs-Guided Vinyl Rip Splitter

Split a captured vinyl side into tracks using the Discogs release as ground truth.
Core principle: **split on the actual music boundaries in the audio; use Discogs only to
sanity-check count and durations.** Every gate below was validated on real rips in this
session's workflow.

## Step 1 — Fetch the Discogs track list

1. `web_fetch_urls` (or `gsk crawl`) the release URL. Discogs pages render server-side;
   a plain fetch returns the tracklist.
2. Extract per side: track positions (A1, A2, B1...), titles, nominal durations, total
   nominal runtime. Pick the side matching the user's file (position prefixes or runtime).
3. Note the expected **track count for that side** — this is a hard assertion later.
   Discogs durations are often padded 5–15 s (submitter-timed); treat them as weak
   evidence, never as split points.

## Step 2 — Probe and analyze the audio

Run `scripts/analyze_structure.py <audiofile>` (deps: numpy, soundfile, scipy).
It prints format info, full-band quiet regions, the **music-band (200–4000 Hz)
envelope** stats, sustained music runs, interior gaps, and post-music blip
characterization. Read it and decide:

- **Sustained music runs ≥ 2 s = songs.** Isolated 0.5 s blips after the last song are
  runout artifacts (thumps), not music — verify via their dominant frequency (<100 Hz
  dominant, <10 % above 1 kHz).
- **Interior gaps ≥ 1 s between music runs = inter-track gaps.** There must be exactly
  N_tracks − 1 of them. A gap that "disappears" (runs merged) means the threshold was
  too low — the music-band envelope with `p10 + 0.35 × (p90 − p10)` handles
  rumble-heavy rips where plain RMS merges tracks.
- **Lead-in needle drops** (thumps in the first seconds) are 85–99 % sub-100 Hz
  rumble — never treat them as music starts.

## Step 3 — Compute boundaries (hard gates)

For track k with music from `o_k` to `e_k` (from the analyzer):

- `start = o_k − 0.20 s` (0.15 s for tracks after the first), clamped ≥ 0
- `end = e_k + 0.55 s` for a decay ending, `+ 0.85 s` for a slow fade ending,
  **clamped to next track's start − 0.25 s** (no overlap, no shared audio)
- **Runout** (when present and the user wants it kept): from last track's end
  (contiguous, zero gap) to last audible blip + 0.5 s. Confirm what follows is digital
  silence (< −75 dB music-band). Runout is saved **raw** — it *is* the artifact;
  no denoise, edge fades only.
- **Assert** `count == N_tracks` and `end_k < start_{k+1}` for all k. On mismatch,
  dump the analyzer output and re-examine; do NOT force a split.

## Step 4 — Split, clean, validate

1. Write a spec JSON, then run:
   ```
   scripts/split_clean.py --source <rip> --spec spec.json --outdir out/
   scripts/validate_split.py --source <rip> --spec spec.json --dir out/
   ```
   Spec format: `{"source": "...", "tracks": [{"name": "A1 Title", "start": s, "end": e}],
   "runout": {"name": "Side B Runout", "start": s, "end": e}}`
2. Cleaning chain per track (built into the script): median-filter decrackle
   (outlier events ≤ 3 ms interpolated), `highpass=f=32`, `lowpass=f=13000`,
   `afftdn=nr=15:nf=-45:tn=1`, 15 ms fade-in, 150 ms fade-out, 16-bit PCM out at
   source rate.
3. Validation gates (script enforces; fix and re-run on FAIL):
   - 0 clip runs ≥ 2 consecutive samples at full scale
   - first/last 50 ms ≤ −35 dB (no mid-song cuts at edges); music fully contained
   - sample 0 exactly 0.0 (fade-in present) + falling tail RMS (fade-out present)
   - zero music-band windows above threshold in the discarded interior gap
   - no overlap; adjacency to runout exact
4. **Visual check**: read the emitted `val_*.png` spectrograms (first/last 4 s per
   track) yourself, or pass them to `gsk understand_images` — confirm clean attacks,
   natural decays, nothing truncated at file edges.
5. Duration outliers vs Discogs nominal: if one track deviates far beyond the pattern
   of the others (e.g. −15 s when siblings are −6 s), deep-dive the tail in the
   source (music-band level per 0.5 s through the boundary) and prove the decay
   completed before the trim — then attribute the delta to the Discogs listing.

## Step 5 — Deliver

- Deliver audio + validation PNGs via `genspark_deliver_files` (batch, one call).
- If the user wants cloud archiving: `gsk aidrive upload --local_file <f>
  --upload_path "/<Artist> - <Title> (split WAV)/<name>.wav" --confirmed true` per file,
  then `gsk aidrive ls` the folder to verify count and byte sizes.
- Report: per-track measured vs nominal durations, split points on the source
  timeline, what was removed, runout kept/raw, and every gate result.

## Pitfalls seen in practice

- Rips recorded hot: lead-in thumps clip the master — they are noise, do not include.
- Rips recorded quiet with noisy gaps: plain RMS threshold merges tracks; always
  structure-detect on the music-band envelope.
- Runout may be pure digital silence on some rips — say so plainly, keep nothing.
- Discogs nominal durations are the least reliable datum; the audio always wins.
- Never process two sides in one file at once; process one side per file.
