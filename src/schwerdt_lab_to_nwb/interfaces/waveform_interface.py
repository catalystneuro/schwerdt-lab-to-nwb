from warnings import warn

import numpy as np
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
        self._starting_time = 0.0
        self._first_sample_time = None

    def set_aligned_starting_time(self, aligned_starting_time: float) -> None:
        """Shift the spike times in the file by this time in seconds to place them on the session clock."""
        self._starting_time = aligned_starting_time

    def set_first_sample_time(self, first_sample_time: float) -> None:
        """Set the session time of the first raw Neuralynx sample; spikes before it are left out."""
        self._first_sample_time = first_sample_time

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
        """Add the thresholded spikes and their waveforms to the NWB file, one unit per unit ID in the file."""
        spikes_data = self.read_spikes_file()

        spike_times = spikes_data[:, 0] + self._starting_time
        unit_ids = spikes_data[:, 1].astype(int)
        # The lab's waveforms are in microvolts; the NWB Units table stores waveforms in volts
        waveforms = spikes_data[:, 2:] * 1e-6

        num_dropped = 0
        if self._first_sample_time is not None:
            keep = spike_times >= self._first_sample_time
            num_dropped = int((~keep).sum())
            spike_times, unit_ids, waveforms = spike_times[keep], unit_ids[keep], waveforms[keep]

        num_waveform_samples = waveforms.shape[1]
        rate = self.source_data["sampling_frequency"]
        unit_descriptions = {-1: "-1 (poor-quality spikes)", 0: "0 (unsorted spikes)"}
        present_units = ", ".join(unit_descriptions.get(uid, str(uid)) for uid in sorted(set(unit_ids.tolist())))
        description = (
            f"Spikes captured by threshold crossing on the Neuralynx recording of site {recording_site}, as provided "
            f"by the lab. Units in this table: {present_units}. Each spike has its time and its waveform "
            f"({num_waveform_samples} samples at {rate} Hz, converted from microvolts to volts). Spike times are "
            f"sorted within each unit."
        )
        if num_dropped:
            description += (
                f" {num_dropped} spikes with times before the first sample of the raw recording were left out."
            )

        units_table = Units(name="thresholded_units", description=description, waveform_rate=float(rate))
        units_table.add_column(name="unit_name", description="The unit ID in the lab's file.")

        module = get_module(nwbfile, "ecephys", description="Processed electrophysiology data.")
        module.add(units_table)

        electrodes_region = None
        try:
            electrodes_region = [nwbfile.electrodes["location"][:].index(recording_site)]
        except ValueError:
            warn(f"No electrodes found in NWB file for recording site '{recording_site}'.")

        for uid in sorted(set(unit_ids.tolist())):
            in_unit = np.flatnonzero(unit_ids == uid)
            order = in_unit[np.argsort(spike_times[in_unit], kind="stable")]
            units_table.add_unit(
                unit_name=str(uid),
                spike_times=spike_times[order].tolist(),
                # the last dimension is for channels; all waveforms are from the one recording site
                waveforms=waveforms[order][..., np.newaxis],
                electrodes=electrodes_region,
            )
