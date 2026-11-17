# Notes concerning the amjad_2025 conversion

 The `amjad_2025` conversion converts electrophysiological, fast-scan cyclic voltammetry (FSCV), behavioral, and eye-tracking data
from experiments conducted in nonhuman primates using microinvasive probes, as described in
 ["Microinvasive Probes for Monitoring Electrical and Chemical Neural Activity in Nonhuman Primates"](https://www.biorxiv.org/content/10.1101/2025.01.30.635139v1.full.pdf).

## Data exploration

Example sessions structure:

```
data_microinvasiveProbes_manuscript/
├── Monkey P
│   ├── cl3_session126_csc12_100_spikes.mat
│   ├── csc12.ncs
│   └── csc12.plx
├── Monkey T
│ ├── 09132024
│ │  ├── FSCV_trlists_c8dg_09132024_firsthalf.mat
│ │  ├── rawFSCV_09132024_ts_c8dg_ramp_bin.mat
│ │  ├── CSC145.ncs
│ │  ├── CSC146.ncs
│ │  ├── tr_nlx_eye x.mat
│ │  ├── tr_nlx_eye y.mat
│ │  ├── raw fscv with all recorded ch/
│ │  │   ├── c5c_p4a_p1a_p3b_p2e_p1b_c8ds_c8dg_c8c_c8a_001.mat
│ │  │   ├── c5c_p4a_p1a_p3b_p2e_p1b_c8ds_c8dg_c8c_c8a_002.mat
│ │  └── trlists.mat
│ └── 09262024
│   ├── 09262024_tr_nlx_c3bs-c3a.mat
│   ├── 09262024_trlist.mat
│   ├── CSC37.ncs
│   ├── CSC38.ncs
│   ├── CSC145.ncs
│   ├── CSC146.ncs
│   └── trlists.mat
└── Notes.txt
```

### Electrophysiological data

Electrophysiological recordings were made using a unity-gain analog amplifier headstage (Neuralynx, HS-36) with an
input range of ±1 mV at a sampling frequency of 30 (monkey P) or 32 kHz (monkey T), and bandpass filtered from 0.1 Hz
to 7500 Hz (monkey P) or 8000 Hz (monkey T), as given in the .ncs headers. This system also recorded timestamps of identified task events using 8-bit event codes. The ephys and FSCV
systems were synchronized by transmitting uniform “trial-start” event codes to both systems, as detailed in previous work.

EPhys files for the example session `09262024` from monkey T:
- `CSC37.ncs` - Raw signals from site c3bs, sampled at 32 kHz, recorded using Neuralynx system.
- `CSC38.ncs` - Raw signals from site c3a, sampled at 32 kHz, recorded using Neuralynx system.
- `09262024_tr_nlx_c3bs-c3a.mat` - Processed LFP signals from site c3bs with respect to c3a, sampled at 1000 Hz, aligned to the initial cue start. (30 second mark aligns to initial cue start).
Spikes for the example session `cl3_session126` from monkey P:
- `cl3_session126_csc12_100_spikes.mat` - This is the EPhys captured and thresholded spike data from site cl3. Each row contains the initial time stamp for the waveform, the unit ID, followed by the detected waveform samples (48 points long sampled at 32 kHz).
- `csc12.plx` - Plexon file containing raw signals and spike data from site cl3.

### FSCV data

- `raw fscv data with all recorded ch/` - Raw FSCV data, the frequency of samples recorded was 214 per FSCV scan, and the scan frequency was 10Hz, therefore each one minute recording has 2140*60=128400 samples (rows of each cell)
- `c5c_p4a_p1a_p3b_p2e_p1b_c8ds_c8dg_c8c_c8a_001.mat` - each file contains one minute of recording where:
  - column 1: timestamps from the start of each 1 minute recording. The frequency of samples recorded was 214 per FSCV scan, and the scan frequency was 10Hz, therefore each one minute recording has 2140*60=128400 samples (rows of each cell)
  - column 2: raw fscv potential values (in volts) recorded from site c8dg which is later converted to current
  - column 3: potential of the ramp signal applied in volts
  - column 4: binary data where 1 indicates when a new ramp begins (ramp = scan, 10 ramps per minute)

- `FSCV_trlists_c8dg_09132024_firsthalf.mat` - Processed FSCV data, aligned to behavioral events, fscv contains processed (PCA extracted) signals from the site name that is mentioned in fscvnames (c8dg). eventmap contains information about what each behavioral code in trlist.NlxEventTTL means.

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

The raw FSCV minute files run on their own clock: file k starts at 60(k-1) s and the files have no gaps. For each
trial, `trlist.eventsfscv` lists every FSCV scan in the 60 s trial window with its FSCV-clock time (column 1) and its
Neuralynx timestamp (column 4). The conversion fits a line to these pairs over all trials and maps every scan time
to the session clock with it (`get_fscv_to_session_time` in `utils/utils.py`). The FSCV clock runs about 10 ppm slow
of Neuralynx, and the fit residual is at most about one scan (0.1 s). The rows that pad the window of a trial cut off
by the end of the FSCV recording (FSCV time 0) are left out of the fit.

The published version 0.261012.0921 interpolated the FSCV times against `tsfscv`, which is a Neuralynx timestamp and
not an FSCV-clock time, so the whole series started at the first trial center (issues
https://github.com/catalystneuro/schwerdt-lab-to-nwb/issues/30 and https://github.com/catalystneuro/schwerdt-lab-to-nwb/issues/31).

This approach guarantees that behavioral, ephys, and FSCV data are temporally synchronized for downstream analysis.

### Trial-aligned FSCV data

Trial-aligned FSCV signals (such as dopamine, pH, motion, and oxidation current) are now stored in the NWB file using a `TimeIntervals` table within a processing module. Each row of the table corresponds to a trial, with `start_time` and `stop_time` matching the trial's interval. Additional columns store the trial-aligned signals and metadata for each trial:

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

- **Thresholded spike data from .mat files (e.g., `cl3_session126_csc12_100_spikes.mat`)**: This data is added to a separate `Units` table within the processed ephys data module (`ecephys`). Each row in this table includes the spike times for each unit ID, with their detected waveform samples. This table is accessible via `nwbfile.processing["ecephys"].data_interfaces["thresholded_units"]`.

## Changes after the reproduction findings (issues #30 and #31)

- Raw ephys, eye tracking and spike times: see the clock section above. For Monkey P (2018) the .ncs timestamps count
  from the start of the acquisition software (first record at 6800.666 s) and the spike times use the same clock, so
  the raw series is shifted by 6800.666 s and the spike times are kept as they are.
- Plexon units are read with neo 0.14.6, which reads the PLX timestamps as unsigned. Older neo versions placed spikes
  2**32 ticks (4294.967 s) too early and dropped some. Spike times are sorted within each unit, and units are named by
  their Plexon id (`ch<channel>#<unit>`, unit #0 is the unsorted unit). For Monkey P only the units of channel
  `csc12_100` are written.
- Thresholded spikes: waveforms are converted from microvolts to volts, spike times are sorted within each unit, and
  spikes before the first raw sample are left out (7 in Monkey P).
- Events: each event is stored once (the trial windows overlap) with sorted times. Codes 9, 40 and 41 are kept; codes
  that are not in the lab's event map are stored as `TTL code <code>`. Only code 0 is skipped. For Monkey P, the
  strobed event codes of `csc12.plx` are stored by code, since no code map is available for that session.
- LFP: written with `conversion=1.0`, since the lab's values are already in volts. Joined trial windows keep at least
  half a sample between timestamps. The description no longer calls it beta-band.
- Raw FSCV: stored in nanoamperes with `conversion=1e-9`, so it reads as amperes.
- Trial-aligned FSCV: one row for every trial with data, with `good` as given by the lab and a `trial_index` column.
- The raw series description gives the DSP filter settings from the .ncs headers (high cut 8000 Hz in the 2024
  sessions, 7500 Hz for Monkey P).
