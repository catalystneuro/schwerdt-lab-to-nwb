from pathlib import Path

import numpy as np
from neuroconv import BaseDataInterface
from neuroconv.tools import get_module
from pydantic import FilePath
from pymatreader import read_mat
from pynwb.ecephys import LFP, ElectricalSeries


class NlxLfpRecordingInterface(BaseDataInterface):
    def __init__(
        self,
        file_path: FilePath,
        trials_key: str,
        sampling_frequency: float = 1000.0,
        es_key: str = "lfp_series",
        verbose: bool = False,
    ):
        """
        Initialize the NlxLfpRecordingInterface.

        Parameters
        ----------
        file_path : FilePath
            Path to the processed LFP recording .mat file.
        trials_key : str
            Key in the .mat file dictionary that contains the LFP data stored per trial.
        sampling_frequency : float, optional
            Sampling frequency of the LFP data in Hz. Default is 1000.0 Hz.
        es_key : str, optional
            Key for the electrical series in the NWB file. Default is "lfp_series".
        verbose : bool, optional
            Whether to print verbose output during processing.
        """

        super().__init__(file_path=file_path, trials_key=trials_key, sampling_frequency=sampling_frequency)
        self._timestamps = None
        self.es_key = es_key
        self.verbose = verbose

    def read_data(self) -> np.ndarray:
        """
        Read LFP data from a .mat file using the specified trials key.

        Returns
        -------
        np.ndarray
            The LFP data for each trial as loaded from the .mat file.

        Raises
        ------
        ValueError
            If the file format is not .mat.
        KeyError
            If the specified trials key is not found in the .mat file.
        """
        file_path = Path(self.source_data["file_path"])
        file_path_suffix = file_path.suffix.lower()
        if file_path_suffix != ".mat":
            raise ValueError(f"Unsupported file format: {file_path_suffix}. Only .mat files are supported.")

        lfp_list_from_mat = read_mat(file_path)
        trials_key = self.source_data.get("trials_key", "tr_nlx")
        if trials_key not in lfp_list_from_mat:
            raise KeyError(f"Key '{trials_key}' not found in the .mat file.")

        return lfp_list_from_mat[trials_key]

    def generate_timestamps_from_trial_start_times(
        self, trial_start_times: list[float], time_offset: float = 30.0
    ) -> np.ndarray:
        """
        Generate timestamps for each trial, relative to the trial start times, with a specified time offset.

        Parameters
        ----------
        trial_start_times : list[float]
            List of trial start times (in seconds).
        time_offset : float, optional
            Time (in seconds) subtracted from each trial start time to align the timestamps. Default is 30.0.

        Returns
        -------
        np.ndarray
            Array of timestamps for each trial, where each row corresponds to the timestamps for a single trial.
        """
        lfp_per_trial = self.read_data()
        num_samples_per_trial = len(lfp_per_trial[0])
        relative_segment_timestamps = np.arange(num_samples_per_trial) / self.source_data["sampling_frequency"]
        segment_timestamps = []
        for trial_start in trial_start_times:
            segment_start = trial_start - time_offset  # since trial starts 30 seconds in
            timestamps = segment_start + relative_segment_timestamps
            segment_timestamps.append(timestamps)

        timestamps = np.stack(segment_timestamps)

        return timestamps

    def add_lfp_to_nwbfile(self, nwbfile, metadata: dict, time_offset: float = 30.0, stub_test: bool = False) -> None:
        """ """
        lfp_data = self.read_data()
        if not isinstance(lfp_data, list):
            raise ValueError("LFP data should be a list of trials, each containing an array of LFP traces.")
        num_trials = len(lfp_data)
        if stub_test:
            num_trials = min(num_trials, 100)
        lfp_traces = np.stack(lfp_data[:num_trials])  # shape (num_trials, num_samples)
        trials = nwbfile.trials
        if trials is None:
            raise ValueError("NWBFile does not contain trials. Please add trials before adding LFP data.")
        trial_start_times = trials["start_time"][:num_trials]
        timestamps = self.generate_timestamps_from_trial_start_times(
            trial_start_times=trial_start_times,
            time_offset=time_offset,
        )
        lfp_traces = np.concatenate(lfp_traces)
        lfp_traces = lfp_traces[:, np.newaxis]

        lfp_channel_ids = [0]  # TODO: this should be the channel IDs for the LFP traces, currently hardcoded to 0
        lfp_electrodes = nwbfile.electrodes.create_region(
            name="electrodes",
            region=lfp_channel_ids,
            description="LFP electrodes table region",
        )
        raw_electrical_series = nwbfile.acquisition["electrical_series"]
        lfp_electrical_series = ElectricalSeries(
            # TODO: add metadata for LFP series
            name="lfp_series",  # metadata["Ecephys"][self.es_key]["name"]
            description="The LFP series",  # metadata["Ecephys"][self.es_key]["description"]
            data=lfp_traces,
            electrodes=lfp_electrodes,
            timestamps=np.concatenate(
                timestamps
            ),  # Warn timestamps are concatenated across trials and num trials doesn't match num samples
            conversion=raw_electrical_series.conversion,
        )
        lfp = LFP(electrical_series=lfp_electrical_series)
        ecephys_module = get_module(
            nwbfile=nwbfile,
            name="ecephys",
            description="Intermediate data from extracellular electrophysiology recordings, e.g., LFP.",
        )
        ecephys_module.add(lfp)

    def add_to_nwbfile(self, nwbfile, metadata: dict, stub_test: bool = False) -> None:
        self.add_lfp_to_nwbfile(nwbfile, metadata, stub_test=stub_test)
