import datetime
import re
from pathlib import Path

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
