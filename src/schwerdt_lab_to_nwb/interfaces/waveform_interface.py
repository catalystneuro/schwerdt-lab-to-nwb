from warnings import warn

import numpy as np
import pandas as pd
from neuroconv import BaseDataInterface
from neuroconv.tools import get_module
from pydantic import FilePath
from pymatreader import read_mat
from pynwb import NWBFile
from pynwb.misc import Units


class WaveformInterface(BaseDataInterface):
    def __init__(
        self,
        file_path: FilePath,
        spikes_data_key: str,
        sampling_frequency: float,
        verbose: bool = False,
    ):
        """
        Initialize the WaveformInterface.

        The interface to add data from EPhys captured and thresholded spike data from a recording site as DynamicTable.
        Each row contains the initial time stamp for the waveform, the unit ID, followed by the detected waveform samples (48 points long sampled at 32 kHz).

        Parameters
        ----------
        file_path : FilePath
            Path to the .mat file containing the waveform data.
        spikes_data_key : str
            Key in the .mat file dictionary that contains the waveform data.
        sampling_frequency : float, optional
            Sampling frequency of the LFP data in Hz. Default is 1000.0 Hz.
        verbose : bool, optional
            Whether to print verbose output during processing.
        """

        super().__init__(file_path=file_path, spikes_data_key=spikes_data_key, sampling_frequency=sampling_frequency)
        self.verbose = verbose

    def read_spikes_file(self):
        """Read spike data from a .mat file."""
        spikes_data = read_mat(self.source_data["file_path"])
        spikes_data_key = self.source_data["spikes_data_key"]
        if spikes_data_key not in spikes_data:
            raise KeyError(f"Key '{spikes_data_key}' not found in the .mat file.")
        return spikes_data[spikes_data_key]

    def add_spikes_to_nwbfile(
        self,
        nwbfile: NWBFile,
        recording_site: str,
    ):
        """Add spike data from a .mat file to an NWB file.

        This .mat file contains the EPhys captured and thresholded spike data from a recording site.
        Each row contains the initial time stamp for the waveform, the unit ID, followed by the
        detected waveform samples (48 points long sampled at 32 kHz).

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the spike data will be added.
        recording_site : str
            The recording site identifier (e.g., 'c5d').
        """

    def add_to_nwbfile(
        self,
        nwbfile: NWBFile,
        metadata: dict | None,
        recording_site: str,
    ) -> None:
        """Add waveform data to the NWB file."""
        spikes_data = self.read_spikes_file()

        waveforms = spikes_data[:, 2:]

        num_waveform_samples = waveforms.shape[1]
        rate = self.source_data["sampling_frequency"]
        description = (
            f"EPhys captured and thresholded spike data from site {recording_site}. "
            f"Each row contains the initial time stamp for the waveform, the unit ID "
            f"(-1 indicates a poor-quality spike), followed by the detected waveform "
            f"samples ({num_waveform_samples}) points long sampled at {rate} Hz)."
        )

        df = pd.DataFrame(
            spikes_data,
            columns=["spike_time", "unit_id"] + [f"waveform_sample_{i}" for i in range(num_waveform_samples)],
        )

        units_table = Units(name="thresholded_units", description=description)
        units_table.add_column(name="unit_name", description="The ID of the unit for each spike.")

        module = get_module(nwbfile, "ecephys", description="Processed electrophysiology data.")
        module.add(units_table)

        # electrodes reference
        electrodes_region = None
        try:
            electrodes_region = [nwbfile.electrodes["location"][:].index(recording_site)]
        except ValueError:
            warn(f"No electrodes found in NWB file for recording site '{recording_site}'.")

        # iterate over unique unit ids and add one unit per id
        for uid in sorted(df["unit_id"].unique()):
            unit_rows = df[df["unit_id"] == uid]
            spike_times = unit_rows["spike_time"].to_numpy()
            waveforms = unit_rows[[c for c in df.columns if c.startswith("waveform_sample_")]].to_numpy()
            waveforms = waveforms[
                ..., np.newaxis
            ]  # the last dimension is for channels, from the file examples we assume they are from the same channel
            units_table.add_unit(
                unit_name=str(int(uid)),
                spike_times=spike_times.tolist(),
                waveforms=waveforms,
                electrodes=electrodes_region,
            )
