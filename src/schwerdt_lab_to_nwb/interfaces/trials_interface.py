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
    """
    Data interface for adding trial information to an NWBFile from MATLAB .mat files.

    This interface reads trial data (e.g., start/stop times, trial types) from a .mat file and adds it to the NWBFile
    in the standard trials table. The .mat file must contain a key (default: 'trlist') with a dictionary that includes
    at least a 'ts' (timestamps) array and a 'type' array for trial tags.

    Parameters
    ----------
    file_path : FilePath
        Path to the .mat file containing trial data.
    trials_key : str
        Key in the .mat file dictionary that contains the trial data.
    verbose : bool, optional
        Whether to print verbose output during processing.
    """

    keywords = ("behavior",)

    def __init__(self, file_path: FilePath, trials_key: str, verbose: bool = False):
        """
        Initialize the TrialsInterface.

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
        """
        Adds the trials data to the NWB file using the standard NeuroConv interface.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the trials data will be added.
        metadata : dict or None
            Metadata dictionary for the NWB file.
        stub_test : bool, optional
            If True, only a subset of trials will be added for testing.
        """
        self.add_trials_to_nwbfile(nwbfile=nwbfile, metadata=metadata, stub_test=stub_test)
