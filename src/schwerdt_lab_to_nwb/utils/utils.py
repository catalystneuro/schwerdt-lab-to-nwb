import datetime
import re
from pathlib import Path

import numpy as np
from pymatreader import read_mat

# Neuralynx .ncs files: a 16 kB text header followed by records of 512 samples, each stamped with the time (in
# microseconds) of its first sample
NCS_HEADER_SIZE = 16 * 1024
NCS_RECORD_DTYPE = np.dtype(
    [
        ("timestamp", "<u8"),
        ("channel_number", "<u4"),
        ("sampling_frequency", "<u4"),
        ("num_valid_samples", "<u4"),
        ("samples", "<i2", 512),
    ]
)

# Timestamps above this (in seconds, about 1973-03-03) are taken as epoch times, those below as times since the start
# of the Neuralynx acquisition software
EPOCH_TIMESTAMP_THRESHOLD = 1e8


def convert_unix_timestamps_to_datetime(timestamps: list[float]) -> list[datetime.datetime]:
    """
    Convert a list of float Unix timestamps (seconds since epoch) to naive wall-clock datetime.datetime objects.

    The Neuralynx timestamps and the trlist timestamps (e.g. 'ts', 'tsfscv', 'NlxEventTS') store the lab's local
    wall-clock time encoded as if it were UTC. Decoding them as UTC therefore returns the lab's wall-clock time,
    independent of the time zone of the machine running the conversion.

    Parameters
    ----------
    timestamps : list of float
        List of timestamps as floats (seconds since 1970-01-01 00:00:00, lab wall-clock time).

    Returns
    -------
    list of datetime.datetime
        List of corresponding naive datetime.datetime objects in the lab's wall-clock time.
    """
    return [datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).replace(tzinfo=None) for ts in timestamps]


def neuralynx_timestamps_are_epoch(neuralynx_extractor) -> bool:
    """
    Whether the Neuralynx record timestamps of a recording are wall-clock epoch times.

    The 2024 recordings store wall-clock time encoded as a UTC epoch. The 2018 recording of Monkey P (Cheetah 2018)
    stores the time since the acquisition software started instead (its first record is at 6800.666 s), and the
    lab's spike times use that clock as well.
    """
    return neuralynx_extractor.neo_reader.global_t_start > EPOCH_TIMESTAMP_THRESHOLD


def get_neuralynx_starting_time(neuralynx_extractor, session_start_time: datetime.datetime) -> float:
    """
    Get the time (in seconds) of the first Neuralynx sample on the session clock.

    Neo reports the Neuralynx sample times relative to the first sample, so data read from Neuralynx start at 0 s.
    This returns the shift that places them on the session clock.

    - Epoch timestamps (2024 sessions): the time of the first sample relative to the session start time.
    - Timestamps relative to the start of the acquisition software (Monkey P, 2018): the session clock is that
      clock, so the shift is the timestamp of the first sample itself.

    Parameters
    ----------
    neuralynx_extractor : NeuralynxRecordingExtractor
        The extractor whose neo reader holds the timestamp of the first sample.
    session_start_time : datetime.datetime
        The session start time (the 'recording_opened' time from the Neuralynx header).

    Returns
    -------
    float
        The time of the first sample in seconds on the session clock.
    """
    global_t_start = neuralynx_extractor.neo_reader.global_t_start
    if not neuralynx_timestamps_are_epoch(neuralynx_extractor):
        return float(global_t_start)
    first_sample_time = convert_unix_timestamps_to_datetime([global_t_start])
    return convert_timestamps_to_relative_timestamps(timestamps=first_sample_time, start_time=session_start_time)[0]


def get_fscv_to_session_time(
    eventsfscv: list[np.ndarray], session_start_time: datetime.datetime
) -> tuple[float, float]:
    """
    Fit the mapping from the FSCV file clock to the session clock.

    Each trial's 'eventsfscv' table holds, for every FSCV scan in the trial window, the FSCV file-clock time of the
    scan (column 0) and the Neuralynx timestamp of the same scan (column 3). The raw FSCV minute files are gapless and
    run on one clock that drifts from Neuralynx by about 10 ppm, so a linear fit over all scans maps the FSCV clock to
    Neuralynx time to within about one scan (0.1 s). The window of a trial truncated by the end of the FSCV recording
    is padded with rows whose FSCV time is 0; these rows, and rows without a Neuralynx timestamp, are left out.

    Parameters
    ----------
    eventsfscv : list of np.ndarray
        The per-trial 'eventsfscv' tables (scans x columns).
    session_start_time : datetime.datetime
        The session start time.

    Returns
    -------
    tuple of float
        (slope, offset) such that session time = slope * FSCV time + offset, in seconds.
    """
    table = np.concatenate([np.asarray(trial_table, dtype=float) for trial_table in eventsfscv if len(trial_table)])
    valid = (table[:, 0] > 0) & (table[:, 3] > EPOCH_TIMESTAMP_THRESHOLD)
    fscv_times, neuralynx_timestamps = table[valid, 0], table[valid, 3]
    session_start_epoch = session_start_time.replace(tzinfo=datetime.timezone.utc).timestamp()
    slope, offset = np.polyfit(fscv_times, neuralynx_timestamps - session_start_epoch, deg=1)
    return float(slope), float(offset)


def get_unique_sorted_event_times(
    event_times_per_trial: list[np.ndarray], event_codes_per_trial: list[np.ndarray]
) -> dict[int, np.ndarray]:
    """
    Collect the event times per code from the per-trial event windows of a trlist.

    The trial windows (60 s around each trial) overlap, so one event is listed in every window that contains it.
    Each event is kept once, and the times of each code are sorted.

    Returns
    -------
    dict
        Event code -> sorted unique event timestamps (in the units of the input).
    """
    times = np.concatenate([np.atleast_1d(np.asarray(t, dtype=float)) for t in event_times_per_trial])
    codes = np.concatenate([np.atleast_1d(np.asarray(c)).astype(int) for c in event_codes_per_trial])
    return {int(code): np.unique(times[codes == code]) for code in np.unique(codes)}


def get_neuralynx_sampling_frequency(neuralynx_extractor) -> float:
    """
    Measure the sampling frequency of a Neuralynx recording from the timestamps of its .ncs records.

    The header gives the nominal sampling frequency (e.g. 32000 Hz), while the record timestamps follow the actual
    sample clock, which can differ by a few parts per million. Over hours of recording this adds up to tens of
    milliseconds, so the rate is fit to the record timestamps of the first channel of the extractor.

    Parameters
    ----------
    neuralynx_extractor : NeuralynxRecordingExtractor
        The extractor of a single-segment Neuralynx recording.

    Returns
    -------
    float
        The measured sampling frequency in Hz.
    """
    channel_name = neuralynx_extractor.get_property("channel_name")[0]
    file_path = next(
        file_path
        for (name, _), file_path in neuralynx_extractor.neo_reader.ncs_filenames.items()
        if name == channel_name
    )
    records = np.memmap(file_path, dtype=NCS_RECORD_DTYPE, mode="r", offset=NCS_HEADER_SIZE)
    record_start_indices = np.concatenate([[0], np.cumsum(records["num_valid_samples"], dtype=np.int64)[:-1]])
    record_start_times = (records["timestamp"] - records["timestamp"][0]) / 1e6
    seconds_per_sample, _ = np.polyfit(record_start_indices, record_start_times, deg=1)
    return 1 / seconds_per_sample


def set_sampling_frequency(recording, sampling_frequency: float) -> None:
    """
    Set the sampling frequency of a spikeinterface recording without a time vector.

    spikeinterface has no public setter for the sampling frequency, which neuroconv writes as the rate of the series.

    Parameters
    ----------
    recording : BaseRecording
        The recording to update.
    sampling_frequency : float
        The sampling frequency in Hz.
    """
    recording._sampling_frequency = sampling_frequency
    for recording_segment in recording._recording_segments:
        recording_segment.sampling_frequency = sampling_frequency


def convert_timestamps_to_relative_timestamps(
    timestamps: list[datetime.datetime], start_time: datetime.datetime | None = None
) -> list[float]:
    """
    Convert a list of datetime.datetime objects to relative times (in seconds) from a reference start time.

    If no start_time is provided, the first timestamp in the list is used as the reference.

    Parameters
    ----------
    timestamps : list of datetime.datetime
        List of datetime.datetime objects representing event times.
    start_time : datetime.datetime, optional
        Reference datetime from which to calculate relative times. If None, uses the first timestamp in the list.

    Returns
    -------
    list of float
        List of relative times in seconds (float), where the first value is always 0 if start_time is None.

    Raises
    ------
    ValueError
        If any computed relative time is negative (i.e., a timestamp is before the reference start_time).
    """
    start_time = start_time or timestamps[0]
    relative_times = [(ts - start_time.replace(tzinfo=None)).total_seconds() for ts in timestamps]
    if any(relative_time < 0 for relative_time in relative_times):
        raise ValueError("Timestamps contain negative relative times. Ensure that the start time is correct.")
    return relative_times


def get_channel_index_from_lfp_file_path(lfp_file_path: Path, electrode_locations: list[str]) -> int:
    """
    Extract the channel index from the LFP file name and find its index in the provided electrode locations.
    The LFP file name is expected to contain the channel name in the format `*_channelName.mat`, where
    `channelName` is the name of the channel (e.g., '09262024_tr_nlx_c3bs-c3a'). The function will
    extract the first channel name ("c3bs") and find its index in the provided list of electrode locations.

    Parameters
    ----------
    lfp_file_path : Path
        Path to the LFP file.
    electrode_locations : list
        List of electrode locations (channel names) to search for the channel index.

    Returns
    -------
    int
        The index of the channel in the electrode locations list.
    """
    file_name = lfp_file_path.name
    # Extract the part after the last underscore and before .mat
    match = re.search(r"_([^_]+)\.mat$", file_name)
    if not match:
        raise ValueError(f"Filename ({file_name}) does not match expected pattern.")
    channel_part = match.group(1)
    first_channel = channel_part.split("-")[0]
    # Find index in electrode_locations
    try:
        return list(electrode_locations).index(first_channel)
    except ValueError:
        raise ValueError(f"Channel {first_channel} not found in electrode locations.")


def get_event_codes_from_trlist_file_path(
    file_path: Path,
    event_code_rename_map: dict[int, str] | None = None,
    event_codes_to_skip: list[int] | None = None,
) -> dict[int, str]:
    """
    Extract event codes and their names from a trlist file.

    Parameters
    ----------
    file_path : Path
        Path to the trlist .mat file.
    event_code_rename_map : dict[int, str], optional
        Dictionary mapping event codes to new names.
    event_codes_to_skip : list[int], optional
        List of event codes to skip.

    Returns
    -------
    dict[int, str]
        Dictionary mapping event codes to their names.
    """
    event_code_rename_map = event_code_rename_map or {}
    event_codes_to_skip = event_codes_to_skip or []

    data = read_mat(file_path)
    data = data.get("trlists", data)
    eventmap = data.get("eventmap")

    if not eventmap or "Code" not in eventmap or "Name" not in eventmap:
        raise ValueError(f"Invalid 'eventmap' structure in file: {file_path}")

    event_codes = {}
    for code, name in zip(eventmap["Code"], eventmap["Name"]):
        try:
            code = int(code)
        except (TypeError, ValueError):
            continue  # skip non-numeric codes
        if code in event_codes_to_skip:
            continue
        event_codes[code] = event_code_rename_map.get(code, name)

    return event_codes


def get_sorted_plexon_sorting(sorting_extractor, channel_names: list[str] | None = None):
    """
    Build a sorting with the units of the given Plexon channels and their spike times in time order.

    Plexon Offline Sorter files can store spikes out of time order (the unsorted unit #0 of Monkey P's csc12.plx goes
    back in time 4 times). The units are named by their Plexon id ('ch<channel>#<unit>', where unit #0 holds the
    spikes Plexon left unsorted).

    Parameters
    ----------
    sorting_extractor : PlexonSortingExtractor
        The sorting read from the .plx file.
    channel_names : list of str, optional
        Plexon channel names to keep (e.g. ['csc12_100']). All units are kept by default.

    Returns
    -------
    NumpySorting
        The selected units with sorted spike trains and a 'unit_name' property.
    """
    from spikeinterface.core import NumpySorting

    spike_channels = sorting_extractor.neo_reader.header["spike_channels"]
    unit_ids = [
        unit_id
        for unit_id, spike_channel in zip(sorting_extractor.unit_ids, spike_channels)
        if channel_names is None or str(spike_channel["name"]) in channel_names
    ]
    unit_names = {
        unit_id: str(spike_channel["id"]) for unit_id, spike_channel in zip(sorting_extractor.unit_ids, spike_channels)
    }
    units_dict = {unit_id: np.sort(sorting_extractor.get_unit_spike_train(unit_id=unit_id)) for unit_id in unit_ids}
    sorting = NumpySorting.from_unit_dict(
        units_dict_list=[units_dict], sampling_frequency=sorting_extractor.get_sampling_frequency()
    )
    sorting.set_property(key="unit_name", values=[unit_names[unit_id] for unit_id in unit_ids])
    # PlexonSortingInterface.get_metadata reads the recording date from the neo reader
    sorting.neo_reader = sorting_extractor.neo_reader
    sorting.block_index = sorting_extractor.block_index
    return sorting


def drop_spikes_before(sorting, start_time: float):
    """
    Remove the spikes of a sorting whose times are before 'start_time' (in the sorting's own seconds).

    Monkey P's csc12.plx holds 7 spikes with times of 0.0003 to 0.017 s, while its recording starts at 6800.666 s.
    They sit between spikes at the short gaps of csc12.ncs (7536.2, 8437.6 and 12040.2 s), so their times count from
    the start of a recording segment and their session times are lost.

    Returns
    -------
    tuple of (NumpySorting, int)
        The sorting without those spikes, with the same unit ids, properties and neo reader, and the number of
        spikes removed.
    """
    from spikeinterface.core import NumpySorting

    start_frame = start_time * sorting.get_sampling_frequency()
    units_dict, num_dropped = {}, 0
    for unit_id in sorting.unit_ids:
        spike_train = sorting.get_unit_spike_train(unit_id=unit_id)
        keep = spike_train >= start_frame
        num_dropped += int(np.sum(~keep))
        units_dict[unit_id] = spike_train[keep]
    kept = NumpySorting.from_unit_dict(
        units_dict_list=[units_dict], sampling_frequency=sorting.get_sampling_frequency()
    )
    for key in sorting.get_property_keys():
        kept.set_property(key=key, values=sorting.get_property(key))
    for attribute in ("neo_reader", "block_index"):
        if hasattr(sorting, attribute):
            setattr(kept, attribute, getattr(sorting, attribute))
    return kept, num_dropped


def _get_ncs_records(neuralynx_extractor, channel_name: str) -> np.memmap:
    file_path = next(
        file_path
        for (name, _), file_path in neuralynx_extractor.neo_reader.ncs_filenames.items()
        if name == channel_name
    )
    return np.memmap(file_path, dtype=NCS_RECORD_DTYPE, mode="r", offset=NCS_HEADER_SIZE)


def get_neuralynx_sample_times(neuralynx_extractor) -> np.ndarray:
    """
    The time of every sample of a Neuralynx recording, from the timestamps of its .ncs records.

    Each .ncs record is stamped with the time of its first sample; the samples of a record follow at the header
    sampling rate. Recordings with gaps (Monkey P, 2018: 20 short records with jumps of up to 10 ms) need these
    per-record times; times counted at the nominal rate from the start of each segment drift from the record
    timestamps by several milliseconds. The times are relative to the first sample, as neo reports them.

    Parameters
    ----------
    neuralynx_extractor : NeuralynxRecordingExtractor
        The extractor of the recording; the record timestamps of its first channel are used.

    Returns
    -------
    np.ndarray
        The time of each sample in seconds from the first sample.
    """
    records = _get_ncs_records(neuralynx_extractor, channel_name=neuralynx_extractor.get_property("channel_name")[0])
    sampling_frequency = float(records["sampling_frequency"][0])
    num_valid_samples = records["num_valid_samples"].astype(np.int64)
    record_start_times = (records["timestamp"] - records["timestamp"][0]) / 1e6
    record_index = np.repeat(np.arange(len(records)), num_valid_samples)
    first_sample_of_record = np.concatenate([[0], np.cumsum(num_valid_samples)[:-1]])
    sample_in_record = np.arange(num_valid_samples.sum()) - np.repeat(first_sample_of_record, num_valid_samples)
    return record_start_times[record_index] + sample_in_record / sampling_frequency


def get_neuralynx_record_samples(neuralynx_extractor) -> np.ndarray:
    """
    The valid samples of the .ncs records of each channel of a Neuralynx recording, in record order.

    In recordings with short records and timing jumps (Monkey P, 2018), neo's non-strict gap mode returns the
    samples between the first and the last group of short records 1526 samples out of place. Reading the records
    directly keeps each sample with the timestamp of its record (see 'get_neuralynx_sample_times').

    Returns
    -------
    np.ndarray
        int16 array of shape (num_samples, num_channels), in the channel order of the extractor.
    """
    channel_names = neuralynx_extractor.get_property("channel_name")
    traces = []
    reference_timestamps = None
    for channel_name in channel_names:
        records = _get_ncs_records(neuralynx_extractor, channel_name=channel_name)
        if reference_timestamps is None:
            reference_timestamps = records["timestamp"]
        elif not np.array_equal(records["timestamp"], reference_timestamps):
            raise ValueError(f"The .ncs records of {channel_name} have other timestamps than {channel_names[0]}.")
        valid = np.arange(records["samples"].shape[1])[np.newaxis, :] < records["num_valid_samples"][:, np.newaxis]
        traces.append(np.asarray(records["samples"])[valid])
    return np.stack(traces, axis=1)
