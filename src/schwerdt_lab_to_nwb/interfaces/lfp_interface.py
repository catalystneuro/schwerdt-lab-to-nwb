import datetime
from pathlib import Path
from typing import List

import numpy as np
from neuroconv import BaseDataInterface
from neuroconv.tools import get_module
from neuroconv.utils import get_base_schema, get_schema_from_hdmf_class
from pydantic import FilePath
from pymatreader import read_mat
from pynwb.device import Device
from pynwb.ecephys import ElectricalSeries, ElectrodeGroup, FilteredEphys

from schwerdt_lab_to_nwb.utils import (
    convert_timestamps_to_relative_timestamps,
    get_channel_index_from_lfp_file_path,
)


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

    def get_metadata_schema(self) -> dict:
        """
        Compile metadata schema for the RecordingExtractor.

        Returns
        -------
        dict
            The metadata schema dictionary containing definitions for Device, ElectrodeGroup,
            Electrodes, and optionally ElectricalSeries.
        """
        metadata_schema = super().get_metadata_schema()
        metadata_schema["properties"]["Ecephys"] = get_base_schema(tag="Ecephys")
        metadata_schema["properties"]["Ecephys"]["required"] = ["Device", "ElectrodeGroup"]
        metadata_schema["properties"]["Ecephys"]["properties"] = dict(
            Device=dict(type="array", minItems=1, items={"$ref": "#/properties/Ecephys/definitions/Device"}),
            ElectrodeGroup=dict(
                type="array", minItems=1, items={"$ref": "#/properties/Ecephys/definitions/ElectrodeGroup"}
            ),
            Electrodes=dict(
                type="array",
                minItems=0,
                renderForm=False,
                items={"$ref": "#/properties/Ecephys/definitions/Electrodes"},
            ),
        )
        # Schema definition for arrays
        metadata_schema["properties"]["Ecephys"]["definitions"] = dict(
            Device=get_schema_from_hdmf_class(Device),
            ElectrodeGroup=get_schema_from_hdmf_class(ElectrodeGroup),
            Electrodes=dict(
                type="object",
                additionalProperties=False,
                required=["name"],
                properties=dict(
                    name=dict(type="string", description="name of this electrodes column"),
                    description=dict(type="string", description="description of this electrodes column"),
                ),
            ),
        )

        if self.es_key is not None:
            metadata_schema["properties"]["Ecephys"]["properties"].update(
                {self.es_key: get_schema_from_hdmf_class(ElectricalSeries)}
            )
        return metadata_schema

    def get_metadata(self) -> dict:
        """
        Get metadata for the LFP recording interface.

        Returns
        -------
        dict
            Metadata dictionary containing information about the LFP recording.
        """
        metadata = super().get_metadata()
        metadata["Ecephys"]["Device"] = [dict(name="device_ecephys", description="Neuralynx recording")]
        metadata["Ecephys"]["ElectrodeGroup"] = [
            dict(
                name="ElectrodeGroup",
                description="The group of electrodes from the EPhys system (Neuralynx, Digital Lynx SX) implanted in the striatum.",
                device="device_ecephys",
            )
        ]

        if self.es_key is not None:
            metadata["Ecephys"][self.es_key] = dict(
                name=self.es_key, description=f"Acquisition traces for the {self.es_key}."
            )
        return metadata

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

    def reconstruct_continuous_signal_from_trials(
        self,
        trial_start_times: list[float],
        time_offset: float = 30.0,
        stub_test: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Reconstruct a continuous signal and its timestamps from segmented trial data.

        This function aligns and concatenates LFP trial segments into a continuous signal,
        handling gaps and overlaps between trials based on their start times.

        Parameters
        ----------
        trial_start_times : list[float]
            List of trial start times (in seconds).
        time_offset : float, optional
            Time (in seconds) subtracted from each trial start time to align the timestamps. Default is 30.0.
        stub_test : bool, optional
            If True, only a subset of trials will be processed for testing purposes. Default is False

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            continuous_time: 1D array of timestamps for the reconstructed signal.
            continuous_signal: 1D array of the reconstructed continuous signal.
        """
        lfp_per_trial = self.read_data()
        num_trials = len(lfp_per_trial)
        if stub_test:
            num_trials = min(num_trials, 100)
        lfp_per_trial = lfp_per_trial[:num_trials]

        fs = self.source_data["sampling_frequency"]
        num_samples_per_trial = len(lfp_per_trial[0])

        continuous_signal_parts = []
        continuous_time_parts = []
        self._num_gap_samples = 0  # samples inserted as NaN between trial windows that do not touch

        for i, trial_data in enumerate(lfp_per_trial):
            trial_start = trial_start_times[i] - time_offset  # since trial starts 30 seconds in
            trial_time = trial_start + np.arange(num_samples_per_trial) / fs

            # Determine margin for overlap handling
            margin = 0
            if i > 0 and trial_time[0] < continuous_time_parts[-1][-1]:
                margin = int(0.1 * len(trial_data))  # 10% margin on each side

            middle_time = trial_time[margin : len(trial_data)]
            middle_data = trial_data[margin : len(trial_data)]

            if i == 0:
                # First trial, just append
                continuous_signal_parts.append(middle_data)
                continuous_time_parts.append(middle_time)
            else:
                last_timestamp = continuous_time_parts[-1][-1]
                gap = middle_time[0] - last_timestamp - 1 / fs

                if gap > 1 / fs:
                    # Insert NaNs for gaps
                    n_gap = int(np.round(gap * fs))
                    self._num_gap_samples += n_gap
                    continuous_signal_parts.append(np.full(n_gap, np.nan))
                    continuous_time_parts.append(last_timestamp + np.arange(1, n_gap + 1) / fs)
                    mask = middle_time > last_timestamp
                else:
                    # Remove overlapping samples: drop the margin at the end of the previous part, then keep only the
                    # samples of this trial that come at least half a sample after the last kept one. The trial
                    # windows are not on one common sample grid, so the two parts would otherwise interleave or
                    # leave timestamps a few microseconds apart at the junction.
                    if margin:
                        continuous_signal_parts[-1] = continuous_signal_parts[-1][:-margin]
                        continuous_time_parts[-1] = continuous_time_parts[-1][:-margin]
                    mask = middle_time > continuous_time_parts[-1][-1] + 0.5 / fs

                continuous_signal_parts.append(middle_data[mask])
                continuous_time_parts.append(middle_time[mask])

        # convert to single arrays
        continuous_signal = np.concatenate(continuous_signal_parts)
        continuous_time = np.concatenate(continuous_time_parts)

        if not np.all(np.diff(continuous_time) > 0):  # ensure continuous time
            raise ValueError("Timestamps are not strictly increasing. Check the LFP data for inconsistencies.")

        return continuous_time, continuous_signal

    def add_lfp_to_nwbfile(
        self, nwbfile, metadata: dict, trial_start_times: List[datetime.datetime], stub_test: bool = False
    ) -> None:
        """ """
        lfp_data = self.read_data()
        if not isinstance(lfp_data, list):
            raise ValueError("LFP data should be a list of trials, each containing an array of LFP traces.")
        num_trials = len(lfp_data)
        if stub_test:
            num_trials = min(num_trials, 100)

        trial_midpoint_times_dt = trial_start_times[:num_trials]
        session_start_time = None
        if "session_start_time" in metadata["NWBFile"]:
            session_start_time = metadata["NWBFile"]["session_start_time"]
        relative_trial_start_times = convert_timestamps_to_relative_timestamps(
            timestamps=trial_midpoint_times_dt,
            start_time=session_start_time,
        )
        timestamps, lfp_traces = self.reconstruct_continuous_signal_from_trials(
            trial_start_times=relative_trial_start_times,
            time_offset=30.0,
            stub_test=stub_test,
        )
        if lfp_traces.ndim == 1:
            # If lfp_traces is 1D, reshape it to 2D with one channel
            lfp_traces = lfp_traces[:, np.newaxis]
        else:
            raise NotImplementedError(
                "LFP traces with multiple channels are not yet implemented in this interface. Need example data."
            )

        electrode_locations = nwbfile.electrodes.location[:]
        channel_id = get_channel_index_from_lfp_file_path(
            lfp_file_path=Path(self.source_data["file_path"]),
            electrode_locations=electrode_locations,
        )
        # The file name ends with the bipolar pair, e.g. '..._c3bs-c3a.mat'
        site, reference_site = Path(self.source_data["file_path"]).stem.split("_")[-1].split("-")
        # One electrode per data column: the region holds the site, and names its reference
        lfp_electrodes = nwbfile.electrodes.create_region(
            name="electrodes",
            region=[channel_id],
            description=f"The electrode of site {site}; the signal is referenced to site {reference_site}.",
        )
        lfp_metadata = metadata["Ecephys"][self.es_key]

        if self._num_gap_samples:
            joining_note = f"Gaps between windows are filled with NaN ({self._num_gap_samples} samples)."
        else:
            joining_note = "Consecutive windows overlap, so the series has no gaps."
        new_description = (
            f"{lfp_metadata['description']} {joining_note} Site {site} referenced to site {reference_site}."
        )

        lfp_electrical_series = ElectricalSeries(
            name=lfp_metadata["name"],
            description=new_description,
            data=lfp_traces,
            electrodes=lfp_electrodes,
            timestamps=timestamps,
            # The source values are already in volts
            conversion=1.0,
        )
        container = FilteredEphys(electrical_series=lfp_electrical_series)
        ecephys_module = get_module(
            nwbfile=nwbfile,
            name="ecephys",
            description="Intermediate data from extracellular electrophysiology recordings, e.g., LFP.",
        )
        ecephys_module.add(container)

    def add_to_nwbfile(
        self, nwbfile, metadata: dict, trial_start_times: list[datetime.datetime] = None, stub_test: bool = False
    ) -> None:
        self.add_lfp_to_nwbfile(nwbfile, metadata, trial_start_times=trial_start_times, stub_test=stub_test)
