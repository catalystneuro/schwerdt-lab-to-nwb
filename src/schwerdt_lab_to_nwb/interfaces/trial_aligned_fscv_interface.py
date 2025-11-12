from pathlib import Path

import numpy as np
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools import get_module
from pydantic import FilePath
from pymatreader import read_mat
from pynwb import NWBFile
from pynwb.epoch import TimeIntervals


class TrialAlignedFSCVInterface(BaseDataInterface):
    """
    Data interface for adding trial-aligned FSCV data to an NWBFile from MATLAB .mat files.

    This interface reads trial-aligned FSCV data (e.g., dopamine, pH, movement signals) from a .mat file
    and stores them in a TimeIntervals table within a processing module in the NWB file. Each row of the
    TimeIntervals table corresponds to a trial, with columns for trial-aligned signals (such as dopamine,
    pH, motion, and oxidation current) and metadata (such as trial quality).
    """

    keywords = ("behavior", "fscv")

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
            Dictionary containing trial-aligned data, typically with keys for each signal (e.g., 'da', 'ph', 'm', 'iox')
            and metadata (e.g., 'good'), where each entry is an array with one element per trial.

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

        # Handle variations in files
        if "trlists" in trials_list_from_mat and "fscv" in trials_list_from_mat["trlists"]:
            fscv_entries = trials_list_from_mat["trlists"]["fscv"]
            # data in expected format
            dict_fscv_channels = [entry for entry in fscv_entries if isinstance(entry, dict)]
            num_fscv_channels = len(dict_fscv_channels)
            if num_fscv_channels == 1:
                return dict_fscv_channels[0]
            else:
                raise ValueError(
                    f"Expected one FSCV channel in 'trlists.fscv', but found {num_fscv_channels} channels. "
                )

        if trials_key not in trials_list_from_mat:
            raise KeyError(f"Key '{trials_key}' not found in the .mat file.")

        return trials_list_from_mat[trials_key]

    def add_trial_aligned_series_to_nwbfile(self, nwbfile: NWBFile, metadata: dict) -> None:
        """
        Adds the trial-aligned FSCV data to the NWB file as a TimeIntervals table.

        For each trial, a row is added to the TimeIntervals table with start and stop times matching the trial,
        and columns for each trial-aligned signal (e.g., dopamine, pH, motion, oxidation current) and metadata.
        The table is added to a processing module named "fscv".

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the trial-aligned FSCV data will be added.
        metadata : dict
            Metadata dictionary containing at least the NWBFile session start time and FSCV table/column definitions.

        Raises
        ------
        ValueError
            If no trial-aligned FSCV data is found or if the NWB file does not contain trials.
        """

        trial_aligned_data = self.read_data()

        if not trial_aligned_data:
            raise ValueError("No trial-aligned FSCV data found in the specified file.")

        if (trials := nwbfile.trials) is None:
            raise ValueError(
                "No trials found in the NWB file. Please add trials before adding trial-aligned FSCV data."
            )

        trial_aligned_fscv_metadata = metadata["TrialAlignedFSCV"]

        trial_aligned_fscv_table_metadata = trial_aligned_fscv_metadata["table"]
        trial_aligned_fscv_table = TimeIntervals(**trial_aligned_fscv_table_metadata)
        trial_aligned_fscv_table.add_column(
            name="rate", description="The sampling rate of the trial-aligned data in Hz."
        )

        trial_start_times = trials["start_time"][:]
        trial_stop_times = trials["stop_time"][:]
        for start_time, stop_time in zip(trial_start_times, trial_stop_times):
            trial_aligned_fscv_table.add_row(start_time=start_time, stop_time=stop_time, rate=self.sampling_frequency)

        # Cast 'good' column to boolean if it exists
        if "good" in trial_aligned_data:
            new_array = np.asarray(trial_aligned_data["good"]).astype(bool).tolist()
            trial_aligned_data.update(good=new_array)

        num_trials = len(trials)
        for column_metadata in trial_aligned_fscv_metadata["columns"]:
            trial_aligned_series_name = column_metadata["name"]
            trial_aligned_fscv_table.add_column(
                **column_metadata,
                data=trial_aligned_data[trial_aligned_series_name][:num_trials],
            )

        processing_module = get_module(
            nwbfile,
            name="fscv",
            description="Processing module containing trial-aligned FSCV data.",
        )
        processing_module.add(trial_aligned_fscv_table)

    def add_to_nwbfile(
        self,
        nwbfile: NWBFile,
        metadata: dict | None,
    ) -> None:
        """
        Adds the trial-aligned FSCV data to the NWB file.

        This method calls `add_trial_aligned_series_to_nwbfile` to store the trial-aligned signals and metadata
        in a TimeIntervals table within the NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the trials and events data will be added.
        metadata : dict or None
            Metadata dictionary for the NWB file, which should include session start time and FSCV table definitions.
        """
        self.add_trial_aligned_series_to_nwbfile(
            nwbfile=nwbfile,
            metadata=metadata,
        )
