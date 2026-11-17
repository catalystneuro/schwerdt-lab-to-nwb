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
to 7500 Hz (monkey P) or 8000 Hz (monkey T), as given in the .ncs headers. This system also recorded timestamps of identified task events using 8-bit event codes. The ephys and FSCV
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
  - column 2: potential of the ramp signal applied, in volts
  - columns 3 to 18: the recorded channels, in volts, later converted to current; site c8ds is column 7
  - column 19: binary data where 1 marks the centre of a 60 s trial window

### Behavioral data

- `trlists.mat` - Contains behavioral data for each trial in the session. The file includes:
  - `ts`: An array of timestamps for the start of each trial.
  - `type`: An array of trial types or tags.
  - `NlxEventTS`: Nested arrays of event timestamps for each trial.
  - `NlxEventTTL`: Nested arrays of event codes for each trial, which can be mapped to event names using `eventmap`.

This data is used to populate the NWB file's trials table and events table. The trials table includes start and stop times for each trial, while the events table contains detailed event information aligned to the trials.

### Session start time

All timestamps in the NWB file are represented as relative times (in seconds) from the session start time.
The session start time is the `recording_opened` time from the Neuralynx header (New York local time),
which is `2024-09-27 08:49:52` in the example session.

The Neuralynx sample timestamps and the `trlist` timestamps (`ts`, `tsfscv`, `NlxEventTS`, `NlxTS`) store the lab's
local wall-clock time encoded as if it were UTC, so they are decoded as UTC to recover the wall-clock time,
independent of the time zone of the machine running the conversion. In the example session the first trial start
(`ts`) is `2024-09-27 10:07:26.993`, 4654.993 s after the session start.

The first Neuralynx sample is recorded 4612.103 s after `recording_opened` in the example session. The raw ephys,
the eye tracking, and the Plexon and thresholded spike times (which count from the first sample) are shifted by this
time so that they share the clock of the trials, events, LFP and FSCV data.

The Neuralynx header gives a nominal sampling frequency of 32000 Hz, while the timestamps of the .ncs records
(which the spike times follow) give 31999.9624 Hz in the example session. Over the 5.1 h recording the nominal rate
would place the last samples 21.5 ms early, so the raw ephys and eye tracking are written with the rate measured from
the record timestamps, which keeps every sample within 0.7 ms of its recorded time.

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
- The alignment logic is implemented in `MicroinvasiveProbesNWBConverter.temporally_align_data_interfaces`, which finds all trial-start events in each trial, then selects the timestamp closest to the intended trial start from `trlist.ts`.
- The `BehaviorInterface` then uses these aligned times when adding trials and events to the NWB file.

This approach guarantees that behavioral, ephys, and FSCV data are temporally synchronized for downstream analysis.

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

### Trial-aligned FSCV data

`09272024_c8ds_fscv.mat` contains the trial-aligned FSCV signals (such as dopamine, pH, motion, and oxidation current) are now stored in the NWB file using a `TimeIntervals` table within a processing module. Each row of the table corresponds to a trial, with `start_time` and `stop_time` matching the trial's interval. Additional columns store the trial-aligned signals and metadata for each trial:

- `good`: Whether the FSCV data for that trial is considered good quality.
- `da`: PCA extracted dopamine concentration time series.
- `ph`: pH change time series.
- `m`: Motion artifact time series.
- `iox`: Measured oxidation current at 0.6 V.

### Eye tracking

Raw eye-tracking signals recorded by the Neuralynx system are imported and stored in the NWB acquisition as an `EyeTracking`
container containing one `SpatialSeries` that stores the continuous, uncalibrated eye position signal (x, y) in volts.

**Files and code reference**
Raw Neuralynx CSC files: `CSC145.ncs` (y) and `CSC146.ncs` (x).
Implementation: `src/schwerdt_lab_to_nwb/interfaces/eye_tracking_interface.py` (EyeTrackingBehaviorInterface).

## Spikes

Spike data is stored in two locations within the NWB file:

- **Spike-sorted data from Plexon**: This data is added to the main units table under `nwbfile.units`.

- **Thresholded spike data from .mat files (e.g., `csc23_100_40uv.mat`)**: This data is added to a separate `Units` table within the processed ephys data module (`ecephys`). Each row in this table includes the spike times for each unit ID, with their detected waveform samples. This table is accessible via `nwbfile.processing["ecephys"].data_interfaces["thresholded_units"]`.

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
  that are not in the event map are stored as `TTL code <code>`. For Monkey P, the
  strobed event codes of `csc12.plx` are stored by code, since no code map is available for that session.
- LFP: written with `conversion=1.0`, since the source values are already in volts. Joined trial windows keep at least
  half a sample between timestamps. The description no longer calls it beta-band.
- Raw FSCV: stored in nanoamperes with `conversion=1e-9`, so it reads as amperes.
- Trial-aligned FSCV: one row for every trial with data, with `good` as in the source data and a `trial_index` column.
- The raw series description gives the DSP filter settings from the .ncs headers (high cut 8000 Hz in the 2024
  sessions, 7500 Hz for Monkey P).

## Changes after the second reproduction review (issue #32)

- Units: both units tables have `resolution` set to the sample period of the Neuralynx recording. The Plexon units
  are linked to the electrode of the site named in the `.plx` file name.
- Trials: each row is a 60 s window centred on the trial start event (code 128), as in the source data, so
  consecutive windows overlap. The table description says so and lists trial start events that have no row.
- Events: the reward condition codes are described from the reward events of the session. Code 0 is no longer
  skipped; it is stored as `TTL code 0` (826 events in Monkey P, where it occurs once per trial). For Monkey P the
  table describes the Plexon event codes.
- Eye tracking: written as stored (ADC counts) with the conversion to volts from the .ncs header. x is `CSC146.ncs`
  and y is `CSC145.ncs`, following the session notes. `trlists.nlxnames` and the files `tr_nlx_eye x.mat` and
  `tr_nlx_eye y.mat` name the two channels the other way round (`tr_nlx_eye x.mat` holds CSC145), which is an open
  question for the lab.
- Monkey P clock: the times count from the start of the acquisition software. The last sample is at 18786.083 s,
  which is 49 s after the file was closed if counted from the session start time (the time the file was created),
  so the clock started at least 49 s before the session start time.
- Not converted: `trlists.fscv` of 09262024 holds trial-aligned FSCV for sites c9a, c8a, c8c, c8dg and c8ds. The
  publication uses only the LFP of this session, and the notes of 09272024 ask to keep unpublished FSCV sites out
  of the public data.
