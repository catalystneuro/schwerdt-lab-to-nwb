import datetime
from collections import defaultdict
from pathlib import Path
from typing import List
from warnings import warn

import numpy as np
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools import get_module
from pydantic import FilePath
from pymatreader import read_mat
from pynwb import NWBFile

from schwerdt_lab_to_nwb.utils import (
    convert_timestamps_to_relative_timestamps,
    convert_unix_timestamps_to_datetime,
)


class BehaviorInterface(BaseDataInterface):
    """
    Data interface for adding trial and event information to an NWBFile from MATLAB .mat files.

    This interface reads trial data (e.g., start/stop times, trial types) and event data (e.g., timestamps, event codes)
    from a .mat file and adds them to the NWBFile. Trial data is added to the standard trials table, while event data
    is added using an AnnotatedEventsTable.

    The .mat file must contain a key (default: 'trlist') with a dictionary that includes at least:
    - 'ts': an array of timestamps for trials.
    - 'type': an array of trial tags.
    - 'NlxEventTS': nested arrays of event timestamps per trial.
    - 'NlxEventTTL': nested arrays of event codes per trial.

    Parameters
    ----------
    file_path : FilePath
        Path to the .mat file containing trial and event data.
    trials_key : str
        Key in the .mat file dictionary that contains the trial data.
    verbose : bool, optional
        Whether to print verbose output during processing.
    """

    keywords = ("behavior",)

    def __init__(self, file_path: FilePath, trials_key: str, verbose: bool = False):
        """
        Initialize the BehaviorInterface.

        Parameters
        ----------
        file_path : FilePath
            Path to the .mat file containing trial data.
        trials_key : str
            Key in the .mat file dictionary that contains the trial data.
        verbose : bool, optional
            Whether to print verbose output during processing.
        """
        super().__init__(file_path=file_path, trials_key=trials_key)
        self.verbose = verbose
        # Internal storage for aligned trial start times
        self._aligned_start_times = None

    def read_data(self) -> dict:
        """
        Reads the trials data from the specified .mat file.

        Returns
        -------
        dict
            Dictionary containing trial data, typically with keys like 'ts' (timestamps) and 'type' (trial tags).

        Raises
        ------
        ValueError
            If the file format is not supported.
        KeyError
            If the specified trials_key is not found in the .mat file.
        """
        file_path = Path(self.source_data["file_path"])
        file_path_suffix = file_path.suffix.lower()
        if file_path_suffix != ".mat":
            raise ValueError(f"Unsupported file format: {file_path_suffix}. Only .mat files are supported.")

        trials_list_from_mat = read_mat(file_path)
        # Handle case where trials data is nested under 'trlists'
        if "trlists" in trials_list_from_mat:
            trials_list_from_mat = trials_list_from_mat["trlists"]
        trials_key = self.source_data.get("trials_key", "trlist")
        if trials_key not in trials_list_from_mat:
            raise KeyError(f"Key '{trials_key}' not found in the .mat file.")

        required_keys = {"ts", "type", "NlxEventTS", "NlxEventTTL"}
        if not required_keys.issubset(trials_list_from_mat[trials_key].keys()):
            missing_keys = required_keys - set(trials_list_from_mat[trials_key].keys())
            raise KeyError(f"The trials data is missing required keys: {missing_keys}")

        return trials_list_from_mat[trials_key]

    def set_aligned_trial_start_times(self, aligned_start_times: List[datetime.datetime]) -> None:
        """
        Sets the trial start times to an externally provided list of aligned start times.

        Parameters
        ----------
        aligned_start_times : list of datetime.datetime
            List of aligned trial start times as datetime objects.
        """
        self._aligned_start_times = aligned_start_times

    def add_trials_to_nwbfile(self, nwbfile: NWBFile, metadata: dict, stub_test: bool = False) -> None:
        """
        Adds the trials data to the NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the trials data will be added.
        metadata : dict
            Metadata dictionary containing at least the NWBFile session start time.
        stub_test : bool, optional
            If True, only a subset of trials will be added for testing.

        Raises
        ------
        ValueError
            If no trials data is found.
        KeyError
            If the trials data does not contain a 'ts' key.
        """
        trials_data = self.read_data()
        if not trials_data:
            raise ValueError("No trials data found in the specified file.")

        if "ts" not in trials_data:
            raise KeyError("The trials data must contain a 'ts' key with timestamps.")

        num_trials = len(trials_data["ts"])
        if stub_test:
            num_trials = min(num_trials, 100)

        unix_timestamps_from_matlab = trials_data["ts"][:num_trials]
        trial_midpoint_times_dt = convert_unix_timestamps_to_datetime(unix_timestamps_from_matlab)

        if self._aligned_start_times is not None:
            if len(self._aligned_start_times) != num_trials:
                raise ValueError("Length of aligned_start_times does not match number of trials in the data.")
            trial_midpoint_times_dt = self._aligned_start_times

        if self._aligned_start_times is not None:
            if len(self._aligned_start_times) != num_trials:
                raise ValueError("Length of aligned_start_times does not match number of trials in the data.")
            start_times_dt = self._aligned_start_times

        session_start_time = None
        if "session_start_time" in metadata["NWBFile"]:
            session_start_time = metadata["NWBFile"]["session_start_time"]
        relative_trial_midpoint_times = convert_timestamps_to_relative_timestamps(
            timestamps=trial_midpoint_times_dt,
            start_time=session_start_time,
        )
        relative_trial_start_times = np.asarray(relative_trial_midpoint_times) - 30.0
        relative_trial_stop_times = np.asarray(relative_trial_midpoint_times) + 30.0

        timeseries = None
        if "ecephys" in nwbfile.processing:
            timeseries = nwbfile.processing["ecephys"]["FilteredEphys"]["differential_lfp_series"]

        trial_types = trials_data["type"][:num_trials]
        nwbfile.add_trial_column(name="midpoint_time", description="The midpoint time of the trial in seconds.")
        for start_time, stop_time, midpoint_time, tag in zip(
            relative_trial_start_times,
            relative_trial_stop_times,
            relative_trial_midpoint_times,
            trial_types,
        ):
            nwbfile.add_trial(
                start_time=start_time,
                stop_time=stop_time,
                midpoint_time=midpoint_time,
                tags=tag,
                timeseries=timeseries,
                check_ragged=False,
            )

    def add_events_to_nwbfile(
        self,
        nwbfile: NWBFile,
        event_mapping: dict,
        metadata: dict | None = None,
        stub_test: bool = False,
    ) -> None:
        """
        Adds event data to the NWB file using an AnnotatedEventsTable.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the event data will be added.
        event_mapping : dict
            Mapping of event codes to labels for the AnnotatedEventsTable.
        metadata : dict or None
            Metadata dictionary for the NWB file, which should include session start time.
        stub_test : bool, optional
            If True, only a subset of events will be added for testing.
        """
        from ndx_events import AnnotatedEventsTable

        annotated_events_metadata = metadata["Events"]["AnnotatedEventsTable"]
        annotated_events = AnnotatedEventsTable(
            name=annotated_events_metadata["name"],
            description=annotated_events_metadata["description"],
        )
        session_start_time = None
        if "session_start_time" in metadata["NWBFile"]:
            session_start_time = metadata["NWBFile"]["session_start_time"]

        trials_data = self.read_data()
        if "NlxEventTS" not in trials_data or "NlxEventTTL" not in trials_data:
            raise KeyError(
                "The trials data must contain 'NlxEventTS' and 'NlxEventTTL' keys for event timestamps and types."
            )
        unix_event_times = trials_data["NlxEventTS"]
        event_types = trials_data["NlxEventTTL"]  # this is per trial
        if stub_test:
            # Limit the number of trials for stub testing
            num_trials = min(len(trials_data["NlxEventTS"]), 100)
            unix_event_times = unix_event_times[:num_trials]
            event_types = event_types[:num_trials]

        # Collect all event times for each event type across all trials
        event_type_to_times = defaultdict(list)

        for unix_event_times_per_trial, event_types_per_trial in zip(unix_event_times, event_types):
            trial_event_times = convert_unix_timestamps_to_datetime(timestamps=unix_event_times_per_trial)
            relative_event_times = convert_timestamps_to_relative_timestamps(
                timestamps=trial_event_times, start_time=session_start_time
            )
            for event_type, relative_event_time in zip(event_types_per_trial, relative_event_times):
                event_type_to_times[event_type].append(relative_event_time)

        # Add grouped event times to the AnnotatedEventsTable
        for event_type, times in event_type_to_times.items():
            label = event_mapping.get(event_type, None)
            if label is None:
                warn(f"Event code '{event_type}' not found in the event mapping. Event will not be added.")
                continue
            annotated_events.add_event_type(
                label=str(label),
                event_description=f"The event times for code '{event_type}'.",
                event_times=times,
                check_ragged=False,
            )

        events_module = get_module(nwbfile, name="events", description="Contains processed event data from Neuralynx.")
        events_module.add(annotated_events)

    def add_to_nwbfile(
        self,
        nwbfile: NWBFile,
        event_mapping: dict,
        metadata: dict | None,
        stub_test: bool = False,
    ) -> None:
        """
        Adds trials and events data to the NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the trials and events data will be added.
        event_mapping : dict
            Mapping of event codes to labels for the AnnotatedEventsTable.
        metadata : dict or None
            Metadata dictionary for the NWB file, which should include session start time.
        stub_test : bool, optional
            If True, only a subset of trials and events will be added for testing.
        """
        self.add_events_to_nwbfile(nwbfile=nwbfile, metadata=metadata, event_mapping=event_mapping, stub_test=stub_test)
        self.add_trials_to_nwbfile(nwbfile=nwbfile, metadata=metadata, stub_test=stub_test)
