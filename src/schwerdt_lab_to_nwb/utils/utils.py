import datetime


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
