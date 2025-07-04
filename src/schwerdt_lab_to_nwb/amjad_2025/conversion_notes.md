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
- `CSC37.ncs` - Raw LFP signals from site c3bs, sampled at 32 kHz, recorded using Neuralynx system.
- `CSC38.ncs` - Raw LFP signals from site c3a, sampled at 32 kHz, recorded using Neuralynx system.
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
- `09262024_trlist.mat` - Behavioral data with each row corresponding to a trial in the session.

### Session start time

All timestamps in the NWB file are represented as relative times (in seconds) from the session start time.
The session start time is set to the time when the Neuralynx system began recording, which is
`2024-09-26 09:01:38.000000` in the example session. The timestamp of the first trial (from `09262024_trlist.mat`)
is `2024-09-26 12:37:27.53965`, which corresponds to a relative time of `12949.053965` seconds after the session start.
