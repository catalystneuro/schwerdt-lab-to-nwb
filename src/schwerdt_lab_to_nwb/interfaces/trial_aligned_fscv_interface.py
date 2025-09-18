from pathlib import Path
from typing import List

import numpy as np
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools import get_module
from pydantic import FilePath
from pymatreader import read_mat
from pynwb import NWBFile, TimeSeries

from schwerdt_lab_to_nwb.utils import (
    reconstruct_continuous_signal_from_trial_aligned_data,
)


class TrialAlignedFSCVInterface(BaseDataInterface):
    """
    Data interface for adding trial-aligned FSCV data to an NWBFile from MATLAB .mat files.
    This interface reads trial-aligned FSCV data (e.g., dopamine, pH, movement signals) from a .mat file
    and adds them to the NWBFile as TimeSeries within a processing module.
    """

    keywords = ("behavior",)

    def __init__(self, file_path: FilePath, trials_key: str, sampling_frequency: float = 10.0, verbose: bool = False):
        """
        Initialize the TrialAlignedFSCVInterface.


        Parameters
        ----------
        file_path : FilePath
            Path to the .mat file containing the trial-aligned FSCV data.
            The expected data is formatted such that each row represents a trial in the session, and each column is
            the PCA extracted dopamine, pH, movement, and the final column is the current at 0.6 V
            (approximate voltage at which dopamine oxidizes).
        sampling_frequency : float
            Sampling frequency of the trial-aligned data in Hz. Default is 10.0 Hz.
        trials_key : str
            Key in the .mat file dictionary that contains the trial data.
        verbose : bool, optional
            Whether to print verbose output during processing.
        """
        super().__init__(file_path=file_path, trials_key=trials_key)
        self.sampling_frequency = sampling_frequency
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
        trials_key = self.source_data["trials_key"]
        if trials_key not in trials_list_from_mat:
            raise KeyError(f"Key '{trials_key}' not found in the .mat file.")

        return trials_list_from_mat[trials_key]

    def add_trial_aligned_series_to_nwbfile(
        self, nwbfile: NWBFile, metadata: dict, aligned_starting_times: List[float], stub_test: bool = False
    ) -> None:
        """
        Adds the trials data to the NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the trials data will be added.
        metadata : dict
            Metadata dictionary containing at least the NWBFile session start time.
        aligned_starting_times : list of float
            Array of starting times for each trial-aligned series. Should match the number of trials in the NWB file.
        stub_test : bool, optional
            If True, only a subset of trials will be added for testing.

        Raises
        ------
        ValueError
            If no trials data is found.
        KeyError
            If the trials data does not contain a 'ts' key.
        """

        trial_aligned_data = self.read_data()

        if not trial_aligned_data:
            raise ValueError("No trial-aligned FSCV data found in the specified file.")

        if "good" in trial_aligned_data:
            invalid_trials = np.where(np.array(trial_aligned_data["good"]) == 0)[0]
            if len(invalid_trials):
                # todo: ADD to as invalid time intervals
                raise NotImplementedError("Adding invalid trials as invalid time intervals is not yet implemented.")
                # for invalid_trial in invalid_trials:
                #     nwbfile.add_invalid_time_interval(
                #         start_time=aligned_starting_times[invalid_trial],
                #         stop_time=aligned_starting_times[invalid_trial] + 1,
                #         time_series=time_series_to_add,
                #         check_ragged=False,
                #     )

        time_series_metadata = metadata["FSCVAnalysis"]["TimeSeries"]
        time_series_to_add = []

        processing_module_metadata = metadata["FSCVAnalysis"]["module"]
        processing_module = get_module(
            nwbfile,
            name=processing_module_metadata["name"],
            description=processing_module_metadata["description"],
        )
        for time_series_info in time_series_metadata:
            time_series_name = time_series_info["name"]
            if time_series_name not in trial_aligned_data:
                raise KeyError(f"Time series '{time_series_name}' not found in the trial-aligned data.")

            continuous_time, continuous_data = reconstruct_continuous_signal_from_trial_aligned_data(
                trial_aligned_data=trial_aligned_data[time_series_name],
                aligned_start_times=aligned_starting_times,
                sampling_frequency=self.sampling_frequency,
            )

            time_series = TimeSeries(
                name=time_series_name,
                description=time_series_info["description"],
                data=continuous_data,
                timestamps=continuous_time,
                unit=time_series_info["unit"],
            )
            time_series_to_add.append(time_series)
            processing_module.add(time_series)

    def add_to_nwbfile(
        self,
        nwbfile: NWBFile,
        aligned_starting_times: list | None,
        metadata: dict | None,
        stub_test: bool = False,
    ) -> None:
        """
        Adds trials and events data to the NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the trials and events data will be added.
        aligned_starting_times : list or np.ndarray
            Array of starting times for each trial-aligned series. Should match the number of trials in the NWB file.
        metadata : dict or None
            Metadata dictionary for the NWB file, which should include session start time.
        stub_test : bool, optional
            If True, only a subset of trials and events will be added for testing.
        """
        self.add_trial_aligned_series_to_nwbfile(
            nwbfile=nwbfile,
            metadata=metadata,
            aligned_starting_times=aligned_starting_times,
            stub_test=stub_test,
        )
