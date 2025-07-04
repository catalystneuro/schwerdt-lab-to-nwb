from pathlib import Path

import numpy as np
from neuroconv.basedatainterface import BaseDataInterface
from pydantic import FilePath
from pymatreader import read_mat
from pynwb import NWBFile

from schwerdt_lab_to_nwb.utils import (
    convert_timestamps_to_relative_timestamps,
    convert_unix_timestamps_to_datetime,
)


class TrialsInterface(BaseDataInterface):
    """ """

    keywords = ("behavior",)

    def __init__(self, file_path: FilePath, trials_key: str, verbose: bool = False):
        """Initialize the TrialsInterface."""
        super().__init__(file_path=file_path, trials_key=trials_key)
        self.verbose = verbose

    def read_data(self) -> dict:
        """
        Reads the trials data from the specified file path.
        This method should be overridden in subclasses to implement specific reading logic.
        """
        file_path = Path(self.source_data["file_path"])
        file_path_suffix = file_path.suffix.lower()
        if file_path_suffix != ".mat":
            raise ValueError(f"Unsupported file format: {file_path_suffix}. Only .mat files are supported.")

        trials_list_from_mat = read_mat(file_path)
        trials_key = self.source_data.get("trials_key", "trlist")
        if trials_key not in trials_list_from_mat:
            raise KeyError(f"Key '{trials_key}' not found in the .mat file.")

        return trials_list_from_mat[trials_key]

    def add_trials_to_nwbfile(self, nwbfile: NWBFile, metadata: dict, stub_test: bool = False) -> None:
        """
        Adds the trials data to the NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the trials data will be added.
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
        start_times_dt = convert_unix_timestamps_to_datetime(unix_timestamps_from_matlab)

        session_start_time = None
        if "session_start_time" in metadata["NWBFile"]:
            session_start_time = metadata["NWBFile"]["session_start_time"]
        relative_start_times = convert_timestamps_to_relative_timestamps(
            timestamps=start_times_dt, start_time=session_start_time
        )
        relative_stop_times = relative_start_times[1:] + [np.nan]

        trial_types = trials_data["type"][:num_trials]
        for start_time, stop_time, tag in zip(relative_start_times, relative_stop_times, trial_types):
            nwbfile.add_trial(
                start_time=start_time,
                stop_time=stop_time,
                tags=tag,
                check_ragged=False,
            )

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict | None, stub_test: bool = False) -> None:
        self.add_trials_to_nwbfile(nwbfile=nwbfile, metadata=metadata, stub_test=stub_test)
