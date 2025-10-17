# Notes concerning the choi_2025 conversion

## Data exploration

Example directory structure:

```
├── Monkey P
│ └── cl3_session126_csc12_100_spikes.mat
├── Monkey T
│ ├── 09132024
│ │ ├── FSCV_trlists_c8dg_09132024_firsthalf.mat
│ │ └── rawFSCV_09132024_ts_c8dg_ramp_bin.mat
│ └── 09262024
│     ├── 09262024_tr_nlx_c3bs-c3a.mat
│     ├── 09262024_trlist.mat
│     ├── CSC37.ncs
│     ├── CSC37_0001.ncs
│     ├── CSC38.ncs
│     └── CSC38_0001.ncs
└── Notes.txt
```

### Electrophysiological data

Electrophysiological recordings were made using a unity-gain analog amplifier headstage (Neuralynx, HS-36) with an
input range of ±1 mV at a sampling frequency of 30 (monkey P) or 32 kHz (monkey T), and bandpass filtered from 0.1 Hz
to 7500 Hz. This system also recorded timestamps of identified task events using 8-bit event codes. The ephys and FSCV
systems were synchronized by transmitting uniform “trial-start” event codes to both systems, as detailed in previous work.

LFP
- `CSC37.ncs` - Raw signals from site c3bs, sampled at 32 kHz, recorded using Neuralynx system.
- `CSC38.ncs` - Raw signals from site c3a, sampled at 32 kHz, recorded using Neuralynx system.
- `09262024_tr_nlx_c3bs-c3a.mat` - Processed LFP signals from site c3bs with respect to c3a, sampled at 1000 Hz, aligned to the initial cue start. (30 second mark aligns to initial cue start).
Spikes
- `cl3_session126_csc12_100_spikes.mat` - This is the EPhys captured and thresholded spike data from sites ??. Each row contains the initial time stamp for the waveform, the unit ID, followed by the detected waveform samples (48 points long sampled at 32 kHz).

### FSCV data

- `rawFSCV_09132024_ts_c8dg_ramp_bin.mat` - Raw FSCV data, the frequency of samples recorded was 214 per FSCV scan, and the scan frequency was 10Hz, therefore each one minute recording has 2140*60=128400 samples (rows of each cell)
- column 1: timestamps from the start of each 1 minute recording. The frequency of samples recorded was 214 per FSCV scan, and the scan frequency was 10Hz, therefore each one minute recording has 2140*60=128400 samples (rows of each cell)
- column 2: raw fscv potential values (in volts) recorded from site c8dg which is later converted to current
- column 3: potential of the ramp signal applied in volts
- column 4: binary data where 1 indicates when a new ramp begins (ramp = scan, 10 ramps per minute)

- `FSCV_trlists_c8dg_09132024_firsthalf.mat` - Processed FSCV data, aligned to behavioral events, fscv contains processed (PCA extracted) signals from the site name that is mentioned in fscvnames (c8dg). eventmap contains information about what each behavioral code in trlist.NlxEventTTL means.

### Behavioral data

- `09262024_trlist.mat` - Contains behavioral data for each trial in the session. The file includes:
  - `ts`: An array of timestamps for the start of each trial.
  - `type`: An array of trial types or tags.
  - `NlxEventTS`: Nested arrays of event timestamps for each trial.
  - `NlxEventTTL`: Nested arrays of event codes for each trial, which can be mapped to event names using `eventmap`.

This data is used to populate the NWB file's trials table and events table. The trials table includes start and stop times for each trial, while the events table contains detailed event information aligned to the trials.

### Session start time

All timestamps in the NWB file are represented as relative times (in seconds) from the session start time.
The session start time is set to the time when the Neuralynx system began recording, which is
`2024-09-26 09:01:38.000000` in the example session. The timestamp of the first trial (from `09262024_trlist.mat`)
is `2024-09-26 12:37:27.53965`, which corresponds to a relative time of `12949.053965` seconds after the session start.

## Time alignment between behavior and EPhys/FSCV

To accurately synchronize behavioral events and trial information with electrophysiology (ephys) and fast-scan cyclic
voltammetry (FSCV) data, both systems record a shared "trial-start" TTL event code.

**Alignment procedure:**
1. The Neuralynx ephys system and the behavioral system both record event codes, including a unique TTL code (typically `128`) that marks the start of each trial.
2. For each trial, the behavioral `.mat` file (`trlist`) contains arrays of event timestamps (`NlxEventTS`) and corresponding event codes (`NlxEventTTL`).
3. During conversion, for each trial, we:
    - Find all indices in `NlxEventTTL` where the value equals the trial-start code (`128`).
    - Use these indices to select the corresponding timestamps from `NlxEventTS` for that trial.
    - From these candidate timestamps, select the one closest to the trial's intended start time from `trlist.ts`.
    - This closest timestamp is used as the aligned trial start time on the EPhys/FSCV acquisition clock.
4. The aligned trial start times are set in the BehaviorInterface and used to populate the NWB trials table, ensuring all trial and event times are referenced to the same timeline as the ephys/FSCV recordings.
5. All timestamps are converted to relative times (seconds) from the session start time, which is set to the start of the Neuralynx recording.

**Code reference:**
- The alignment logic is implemented in `Amjad2025NWBConverter.temporally_align_data_interfaces`, which finds all trial-start events in each trial, then selects the timestamp closest to the intended trial start from `trlist.ts`.
- The `BehaviorInterface` then uses these aligned times when adding trials and events to the NWB file.

### Time alignment for raw FSCV data

To synchronize raw FSCV timestamps with the Neuralynx clock, we use interpolation:

```python
import numpy as np
# original_fscv_timestamps: The raw (unaligned) timestamps from the FSCV system (in seconds, starting from 0.0, sampled at 25kHz)
# fscv_trial_start_times: Trial start times from the FSCV system (from "tsfscv" in the `trlist` .mat file)
# neuralynx_trial_start_times: Aligned trial start times on the Neuralynx clock (from NlxEventTTL and NlxEventTS as described above)

aligned_fscv_timestamps = np.interp(
    x=original_fscv_timestamps,
    xp=fscv_trial_start_times,
    fp=neuralynx_trial_start_times,
)
```

The schematic below illustrates the alignment process. Key event markers (black squares: trial start times from the FSCV system)
are mapped to corresponding timestamps in the Neuralynx system using interpolation (red arrows).

![Alt text](time_alignment_schematic.png

This approach guarantees that behavioral, ephys, and FSCV data are temporally synchronized for downstream analysis.

### Trial-aligned FSCV data

Trial-aligned FSCV signals (such as dopamine, pH, motion, and oxidation current) are now stored in the NWB file using a `TimeIntervals` table within a processing module. Each row of the table corresponds to a trial, with `start_time` and `stop_time` matching the trial's interval. Additional columns store the trial-aligned signals and metadata for each trial:

- `good`: Whether the FSCV data for that trial is considered good quality.
- `da`: PCA extracted dopamine concentration time series.
- `ph`: pH change time series.
- `m`: Motion artifact time series.
- `iox`: Measured oxidation current at 0.6 V.
