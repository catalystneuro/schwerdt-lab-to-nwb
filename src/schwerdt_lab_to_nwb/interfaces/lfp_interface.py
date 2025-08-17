from pathlib import Path

import numpy as np
from neuroconv import BaseDataInterface
from neuroconv.tools import get_module
from neuroconv.utils import get_base_schema, get_schema_from_hdmf_class
from pydantic import FilePath
from pymatreader import read_mat
from pynwb.device import Device
from pynwb.ecephys import ElectricalSeries, ElectrodeGroup, FilteredEphys

from schwerdt_lab_to_nwb.utils import get_channel_index_from_lfp_file_path


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
        self, trial_start_times: list[float], time_offset: float = 30.0
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

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            continuous_time: 1D array of timestamps for the reconstructed signal.
            continuous_signal: 1D array of the reconstructed continuous signal.
        """
        lfp_per_trial = self.read_data()

        fs = self.source_data["sampling_frequency"]
        num_samples_per_trial = len(lfp_per_trial[0])

        continuous_signal = []
        continuous_time = []

        for i, trial_data in enumerate(lfp_per_trial):
            trial_start = trial_start_times[i] - time_offset  # since trial starts 30 seconds in
            trial_time = trial_start + np.arange(num_samples_per_trial) / fs
            if i == 0:
                # just add the first trial
                continuous_signal.append(trial_data)
                continuous_time.append(trial_time)
            else:
                last_timestamp = continuous_time[-1][-1]
                gap = trial_time[0] - last_timestamp - 1 / fs  # subtract one sample to avoid tiny overlap
                if gap > 1 / fs:  # more than one sample missing
                    n_gap = int(np.round(gap * fs))
                    continuous_signal.append(np.full(n_gap, np.nan))
                    continuous_time.append(last_timestamp + np.arange(1, n_gap + 1) / fs)

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
            raise ValueError("Timestamps are not strictly increasing. Check the LFP data for inconsistencies.")

        return continuous_time, continuous_signal

    def add_lfp_to_nwbfile(self, nwbfile, metadata: dict, time_offset: float = 30.0, stub_test: bool = False) -> None:
        """ """
        lfp_data = self.read_data()
        if not isinstance(lfp_data, list):
            raise ValueError("LFP data should be a list of trials, each containing an array of LFP traces.")
        num_trials = len(lfp_data)
        if stub_test:
            num_trials = min(num_trials, 100)
        trials = nwbfile.trials
        if trials is None:
            raise ValueError("NWBFile does not contain trials. Please add trials before adding LFP data.")
        trial_start_times = trials["start_time"][:num_trials]

        timestamps, lfp_traces = self.reconstruct_continuous_signal_from_trials(
            trial_start_times=trial_start_times,
            time_offset=time_offset,
            # stub_q
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
        lfp_channel_ids = [channel_id]
        lfp_electrodes = nwbfile.electrodes.create_region(
            name="electrodes",
            region=lfp_channel_ids,
            description="LFP electrodes table region",
        )
        raw_electrical_series = nwbfile.acquisition["electrical_series"]
        lfp_metadata = metadata["Ecephys"][self.es_key]

        lfp_electrical_series = ElectricalSeries(
            name=lfp_metadata["name"],
            description=f"Differential LFP signals from site {electrode_locations[0]} with respect to {electrode_locations[1]}.",
            data=lfp_traces,
            electrodes=lfp_electrodes,
            timestamps=timestamps,
            conversion=raw_electrical_series.conversion,
        )
        container = FilteredEphys(electrical_series=lfp_electrical_series)
        ecephys_module = get_module(
            nwbfile=nwbfile,
            name="ecephys",
            description="Intermediate data from extracellular electrophysiology recordings, e.g., LFP.",
        )
        ecephys_module.add(container)

    def add_to_nwbfile(self, nwbfile, metadata: dict, stub_test: bool = False) -> None:
        self.add_lfp_to_nwbfile(nwbfile, metadata, stub_test=stub_test)
