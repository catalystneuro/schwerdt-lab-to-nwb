import datetime
import re
from pathlib import Path
from typing import List

import numpy as np
from pymatreader import read_mat


def convert_unix_timestamps_to_datetime(timestamps: list[float]) -> list[datetime.datetime]:
    """
    Convert a list of float Unix timestamps (seconds since epoch) to Python datetime.datetime objects.

    Parameters
    ----------
    timestamps : list of float
        List of Unix timestamps as floats (seconds since 1970-01-01 00:00:00 UTC).

    Returns
    -------
    list of datetime.datetime
        List of corresponding datetime.datetime objects in local time.
    """
    return [datetime.datetime.fromtimestamp(ts) for ts in timestamps]


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


def fetch_relative_fscv_start_times_from_trlist(
    file_path: Path,
    trlist_key: str = "trlist",
    time_column_index: int = 3,
    session_start_time: datetime.datetime | None = None,
) -> List[float]:
    """
    Fetch the 'eventsfscv' timestamps from a .mat file's trials list and convert them to relative times.

    Parameters
    ----------
    file_path : Path
        Path to the .mat file containing the trials list.
    trlist_key : str, default 'trlist'
        Key in the .mat file where the trials list is stored.
    time_column_index : int, default 3
        Index of the column in 'eventsfscv' that contains the timestamps.
    session_start_time : datetime.datetime, optional
        Reference start time to convert timestamps to relative times. If None, the first timestamp is used.

    Returns
    -------
    List[float]
        List of relative start times in seconds.
    """
    trials_list_from_mat = read_mat(file_path)
    if trlist_key not in trials_list_from_mat.keys():
        # TODO: how to handle this more gracefully?
        if "trlists" in trials_list_from_mat:
            trials_list_from_mat = trials_list_from_mat["trlists"]
            if trlist_key not in trials_list_from_mat:
                raise ValueError(f"Key '{trlist_key}' not found in the .mat file.")

    fscv_events = trials_list_from_mat[trlist_key]["eventsfscv"]
    unix_timestamps_per_trial = [fscv_events[trial_id][:, time_column_index][0] for trial_id in range(len(fscv_events))]
    start_times_dt = convert_unix_timestamps_to_datetime(unix_timestamps_per_trial)
    relative_start_times = convert_timestamps_to_relative_timestamps(
        timestamps=start_times_dt,
        start_time=session_start_time,
    )
    return relative_start_times


def reconstruct_continuous_signal_from_trial_aligned_data(
    trial_aligned_data: List[np.ndarray],
    aligned_start_times: List[float],
    sampling_frequency: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Reconstruct a continuous signal from trial-aligned data segments.

    Parameters
    ----------
    trial_aligned_data : List[np.ndarray]
        List of 1D numpy arrays, each representing a trial-aligned data segment.
    aligned_start_times : List[float]
        List of starting times (in seconds) for each trial-aligned segment.
    sampling_frequency : float
        Sampling frequency of the data in Hz.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        A tuple containing:
        - continuous_time: 1D numpy array of timestamps for the continuous signal.
        - continuous_signal: 1D numpy array of the reconstructed continuous signal, with NaNs
          filling any gaps between trials.
    """
    continuous_signal = []
    continuous_time = []

    if len(trial_aligned_data) != len(aligned_start_times):
        raise ValueError(
            f"The number of trial-aligned data segments ({len(trial_aligned_data)}) must match the number of aligned start times ({len(aligned_start_times)})."
        )

    num_samples_per_trial = len(trial_aligned_data[0])
    for trial_index, (trial_data, segment_start_time) in enumerate(zip(trial_aligned_data, aligned_start_times)):
        trial_time = segment_start_time + np.arange(num_samples_per_trial) / sampling_frequency

        if trial_index == 0:
            # just add the first trial
            continuous_signal.append(trial_data)
            continuous_time.append(trial_time)
        else:
            last_timestamp = continuous_time[-1][-1]
            gap = trial_time[0] - last_timestamp - 1 / sampling_frequency  # subtract one sample to avoid tiny overlap
            if gap > 1 / sampling_frequency:  # more than one sample missing
                n_gap = int(np.round(gap * sampling_frequency))
                continuous_signal.append(np.full(n_gap, np.nan))
                continuous_time.append(last_timestamp + np.arange(1, n_gap + 1) / sampling_frequency)

            # clip overlapping samples
            trial_mask = trial_time > last_timestamp
            trial_data = trial_data[trial_mask]
            trial_time = trial_time[trial_mask]

            continuous_signal.append(trial_data)
            continuous_time.append(trial_time)

    # convert to single arrays
    continuous_signal = np.concatenate(continuous_signal)
    continuous_time = np.concatenate(continuous_time)

    if not np.all(np.diff(continuous_time) > 0):  # ensure continuous time
        raise ValueError("Timestamps are not strictly increasing. Check the data for inconsistencies.")

    return continuous_time, continuous_signal
