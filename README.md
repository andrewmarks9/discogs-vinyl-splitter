# README — discogs-vinyl-splitter

Split a captured vinyl side into tracks using a Discogs release as ground truth.
Detects real song boundaries in the audio (rumble-immune), removes turntable noise,
keeps runout as a separate raw file, and validates every split before delivering.

## Install in Claude

The skill is just a folder: `SKILL.md` at its root plus `scripts/`. Claude.ai takes that
folder as a ZIP upload; Claude Code reads it straight from disk. No build step either way.


### Claude.ai (web app)

1. Turn on code execution first: **Settings → Capabilities → Code execution and file
   creation**. Skills that run scripts need it; without it they show greyed out.
2. Open **[Customize → Skills](https://claude.ai/customize/skills)**.
3. Click **+**, then **+ Create skill**, and choose **Upload a skill**.
4. Upload a ZIP whose **top level is the skill folder** — `SKILL.md` must sit at the
   folder root, not at the ZIP root:

   ```bash
   git clone https://github.com/andrewmarks9/discogs-vinyl-splitter
   zip -r discogs-vinyl-splitter.zip discogs-vinyl-splitter -x '*/.git/*'
   ```

   The folder name should stay `discogs-vinyl-splitter` to match the `name` field in
   `SKILL.md` frontmatter.
5. Confirm it appears in your list and is toggled **on**. Claude then picks it up on its
   own whenever a message matches the trigger below, or when you name it explicitly.

On **Team** and **Enterprise** plans an owner must first enable **Skills** and **Code
execution and file creation** in **Organization settings → Plugins & skills**; members may
also need **User-created skills** enabled before they can upload their own.

### Claude Code (terminal)

Clone the folder into a skills directory — Claude Code reads `SKILL.md` from there
directly:

```bash
# personal: loads in every project on this machine
git clone https://github.com/andrewmarks9/discogs-vinyl-splitter \
  ~/.claude/skills/discogs-vinyl-splitter

# or project-scoped: commit it so everyone working in the repo gets it
git clone https://github.com/andrewmarks9/discogs-vinyl-splitter \
  .claude/skills/discogs-vinyl-splitter
```

Then:

- `/skills` lists it; `/discogs-vinyl-splitter` invokes it directly.
- It also loads automatically when a message carries a Discogs release URL plus a rip.
- `SKILL.md` edits are picked up live mid-session. If you created `~/.claude/skills/`
  **after** the session started, run `/reload-skills` once so it gets watched.

If you already uploaded it in Claude.ai, Claude Code (v2.1.273+) syncs your account's
skills automatically and `/skills` lists them under **claude.ai sync** — no clone needed.
Note that `~/.claude/skills/` is machine-local: **Cowork and cloud sessions don't read
it**, so for those use the Claude.ai upload instead of the clone.

### Runtime dependencies

The skill shells out to Python with `numpy`, `soundfile`, `scipy`, `matplotlib` and
`ffmpeg` — see [Requirements](#requirements).

- **Claude Code** runs on your machine, so install them there once.
- **Claude.ai** runs in a container that starts without them, and the skill does not
  install packages on its own. The first `analyze_structure.py` call will fail until they
  exist, so either ask Claude to install them up front, or run the splitter locally with
  the CLI flow below.

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
   deliver files + validation spectrograms.

**Optional cloud archive:** if the `gsk` CLI is available in the environment, the output
can also be uploaded to a Genspark AI Drive folder named
`<Artist> - <Title> (split WAV)` — just ask. Without `gsk`, skip this step; everything
else runs on plain Python and `ffmpeg`.

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
