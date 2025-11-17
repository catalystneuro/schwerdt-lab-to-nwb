# Notes concerning the choi_2025 conversion

 The `choi_2025` conversion converts electrophysiological, fast-scan cyclic voltammetry (FSCV), behavioral, and eye-tracking data
from experiments conducted in nonhuman primates using microinvasive probes, as described in
 ["Aseptic, semi-sealed cranial chamber implants for chronic multi-channel neurochemical and electrophysiological neural recording in nonhuman primates"](https://doi.org/10.1016/j.jneumeth.2025.110467).


## Data exploration

Example session structure:

```
Monkey T/ 09272024
├── 09272024_c8ds_fscv.mat
├── CSC145.ncs
├── CSC146.ncs
├── CSC47.ncs
├── CSC7.ncs
├── csc23_100.ncs
├── csc23_100_40uv.mat
├── notes.txt
├── raw fscv data with all recorded ch/
│   ├── c8c_c8ds_c8a_c9a_c8dg_001.mat
│   ├── c8c_c8ds_c8a_c9a_c8dg_002.mat
│   └── c8c_c8ds_c8a_c9a_c8dg_328.mat
├── tr_nlx_c7b-c5c.mat
├── tr_nlx_eye x.mat
├── tr_nlx_eye y.mat
└── trlists.mat
```

### Electrophysiological data

Electrophysiological recordings were made using a unity-gain analog amplifier headstage (Neuralynx, HS-36) with an
input range of ±1 mV at a sampling frequency of 30 (monkey P) or 32 kHz (monkey T), and bandpass filtered from 0.1 Hz
to 7500 Hz. This system also recorded timestamps of identified task events using 8-bit event codes. The ephys and FSCV
systems were synchronized by transmitting uniform “trial-start” event codes to both systems, as detailed in previous work.

LFP
- `CSC7.ncs` - Raw signals from site c5c, sampled at 32 kHz, recorded using Neuralynx system.
- `CSC47.ncs` - Raw signals from site c7b, sampled at 32 kHz, recorded using Neuralynx system.
- `tr_nlx_c7b-c5c.mat` - Processed LFP signals from site c7b with respect to c5c, sampled at 1000 Hz, aligned to the initial cue start. (30 second mark aligns to initial cue start).
Spikes
- `csc23_100_40uv.mat` - This is the EPhys captured and thresholded spike data from site c5d. Each row contains the initial time stamp for the waveform, the unit ID, followed by the detected waveform samples (48 points long sampled at 32 kHz).

### FSCV data

- `raw fscv data with all recorded ch/` - Raw FSCV data, the frequency of samples recorded was 214 per FSCV scan, and the scan frequency was 10Hz, therefore each one minute recording has 2140*60=128400 samples (rows of each cell)
- `c8c_c8ds_c8a_c9a_c8dg_001.mat` - each file contains one minute of recording where:
  - column 1: timestamps from the start of each 1 minute recording. The frequency of samples recorded was 214 per FSCV scan, and the scan frequency was 10Hz, therefore each one minute recording has 2140*60=128400 samples (rows of each cell)
  - column 2: raw fscv potential values (in volts) recorded from site c8dg which is later converted to current
  - column 3: potential of the ramp signal applied in volts
  - column 4: binary data where 1 indicates when a new ramp begins (ramp = scan, 10 ramps per minute)

### Behavioral data

- `trlists.mat` - Contains behavioral data for each trial in the session. The file includes:
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

To ensure that behavioral events and trial information are accurately aligned with electrophysiology (ephys) and fast-scan cyclic voltammetry (FSCV) data, we use a shared "trial-start" TTL event code recorded by both systems.

**Alignment procedure:**
1. The Neuralynx ephys system and the behavioral system both record event codes, including a unique TTL code (typically `128`) that marks the start of each trial.
2. For each trial, the behavioral `.mat` file (`trlist`) contains arrays of event timestamps (`NlxEventTS`) and corresponding event codes (`NlxEventTTL`).
3. During conversion, for each trial, we:
    - Find all indices in `NlxEventTTL` where the value equals the trial-start code (`128`).
    - Use these indices to select the corresponding timestamps from `NlxEventTS` for that trial.
    - From these candidate timestamps, select the one closest to the trial's intended start time from `trlist.ts`.
    - This closest timestamp is used as the aligned trial start time on the EPhys/FSCV acquisition clock.
4. The aligned trial start times are set in the `BehaviorInterface` and used to populate the NWB trials table, ensuring that all trial and event times are referenced to the same timeline as the ephys/FSCV recordings.
5. All timestamps are converted to relative times (seconds) from the session start time, which is set to the start of the Neuralynx recording.

**Code reference:**
- The alignment logic is implemented in `Amjad2025NWBConverter.temporally_align_data_interfaces`, which finds all trial-start events in each trial, then selects the timestamp closest to the intended trial start from `trlist.ts`.
- The `BehaviorInterface` then uses these aligned times when adding trials and events to the NWB file.

This approach guarantees that behavioral, ephys, and FSCV data are temporally synchronized for downstream analysis.

### Trial-aligned FSCV data

`09272024_c8ds_fscv.mat` contains the trial-aligned FSCV signals (such as dopamine, pH, motion, and oxidation current) are now stored in the NWB file using a `TimeIntervals` table within a processing module. Each row of the table corresponds to a trial, with `start_time` and `stop_time` matching the trial's interval. Additional columns store the trial-aligned signals and metadata for each trial:

- `good`: Whether the FSCV data for that trial is considered good quality.
- `da`: PCA extracted dopamine concentration time series.
- `ph`: pH change time series.
- `m`: Motion artifact time series.
- `iox`: Measured oxidation current at 0.6 V.

### Eye tracking

Raw eye-tracking signals recorded by the Neuralynx system are imported and stored in the NWB acquisition as an `EyeTracking`
container containing one `SpatialSeries` that stores the continuous gaze position time series (x, y).

**Files and code reference**
Raw Neuralynx CSC files: `CSC145.ncs` (y) and `CSC146.ncs` (x).
Implementation: `src/schwerdt_lab_to_nwb/interfaces/eye_tracking_interface.py` (EyeTrackingBehaviorInterface).

## Spikes

Spike data is stored in two locations within the NWB file:

- **Spike-sorted data from Plexon**: This data is added to the main units table under `nwbfile.units`.

- **Thresholded spike data from .mat files (e.g., `csc23_100_40uv.mat`)**: This data is added to a separate `Units` table within the processed ephys data module (`ecephys`). Each row in this table includes the spike times for each unit ID, with their detected waveform samples. This table is accessible via `nwbfile.processing["ecephys"].data_interfaces["thresholded_units"]`.
