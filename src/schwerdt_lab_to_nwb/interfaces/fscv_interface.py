from typing import List

import numpy as np
from ndx_fscv import FSCVExcitationSeries, FSCVResponseSeries
from neuroconv import BaseTemporalAlignmentInterface
from neuroconv.tools.spikeinterface.spikeinterface import _get_null_value_for_property
from neuroconv.utils import get_schema_from_hdmf_class
from pydantic import FilePath
from pymatreader import read_mat
from pynwb import NWBFile
from pynwb.device import Device
from pynwb.ecephys import ElectrodeGroup


class FSCVRecordingInterface(BaseTemporalAlignmentInterface):

    def __init__(
        self,
        file_paths: List[FilePath],
        channel_ids_to_brain_area: dict[int, str],
        data_key: str = "recordedData",
    ):
        """
        Data interface for reading FSCV data files.

        Parameters
        ----------
        file_paths : List[FilePath]
            List of paths to the FSCV data files.
        channel_ids_to_brain_area : dict[int, str]
            Mapping of channel indices (0-based) to brain area names. The keys should correspond to the indices of
            the channels in the FSCV data files.
        data_key : str
            Key in the .mat file dictionary that contains the FSCV data. Default is "recordedData".
        """
        super().__init__(file_paths=file_paths)
        self.channel_ids_to_brain_area = channel_ids_to_brain_area
        self.data_key = data_key
        self._timestamps = None

    def get_metadata_schema(self) -> dict:
        metadata_schema = super().get_metadata_schema()
        # Add FSCV series schemas under "FSCV"
        metadata_schema["properties"]["FSCV"] = dict(
            type="object",
            required=["Device", "ElectrodeGroup", "FSCVResponseSeries", "FSCVExcitationSeries"],
            properties=dict(
                Device=get_schema_from_hdmf_class(Device),
                ElectrodeGroup=get_schema_from_hdmf_class(ElectrodeGroup),
                FSCVResponseSeries=dict(
                    type="object",
                    required=["name", "description", "unit"],
                    properties=dict(
                        name=dict(type="string", default="fscv_response_series"),
                        description=dict(type="string", default="FSCV response current before background subtraction."),
                        unit=dict(type="string", default="amperes"),
                    ),
                ),
                FSCVExcitationSeries=dict(
                    type="object",
                    required=["name", "description", "unit", "scan_frequency", "sweep_rate", "waveform_shape"],
                    properties=dict(
                        name=dict(type="string", default="fscv_excitation_series"),
                        description=dict(type="string", default="FSCV excitation series for applied voltage waveform."),
                        unit=dict(type="string", default="volts"),
                        scan_frequency=dict(type="number", default=10.0, description="in Hz"),
                        sweep_rate=dict(type="number", default=400.0, description="in V/s"),
                        waveform_shape=dict(type="string", default="Triangle"),
                    ),
                ),
            ),
        )

        # Schema definition for arrays
        metadata_schema["properties"]["FSCV"]["definitions"] = dict(
            Device=get_schema_from_hdmf_class(Device),
            ElectrodeGroup=get_schema_from_hdmf_class(ElectrodeGroup),
        )

        return metadata_schema

    def get_metadata(self) -> dict:
        """
        Get metadata for the FSCV recording.

        Returns
        -------
        dict
            Metadata dictionary containing information about the FSCV recording.
        """
        metadata = super().get_metadata()

        metadata["FSCV"] = dict(
            Device=dict(name="device_fscv", description="FSCV recording"),
            ElectrodeGroup=dict(
                name="FSCVElectrodeGroup",
                description="The group of FSCV electrodes.",
                location="unknown",
                device="device_fscv",
            ),
            FSCVResponseSeries=dict(
                name="fscv_response_series",
                description="FSCV response current before background subtraction.",
                unit="amperes",
            ),
            FSCVExcitationSeries=dict(
                name="fscv_excitation_series",
                description="FSCV excitation series for applied voltage waveform.",
                unit="volts",
                scan_frequency=10.0,
                sweep_rate=400.0,
                waveform_shape="Triangle",
            ),
        )

        return metadata

    def read_data(self, conversion_factor: float) -> tuple[np.ndarray, np.ndarray]:
        """
        Reads the FSCV data from the specified files.

        Parameters
        ----------
        conversion_factor : float
            Factor to convert raw signal (V) to current (A).

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            A tuple containing:
            - excitation_series: Array of applied voltages (V).
            - response_series: Array of measured currents (A).
        """
        applied_voltages = []
        channels = []
        for file_path in self.source_data["file_paths"]:
            mat = read_mat(file_path)
            if self.data_key not in mat:
                raise KeyError(f"Key '{self.data_key}' not found in {file_path}")
            data = mat[self.data_key]

            applied_voltages.append(data[:, 1])
            channel_indices = list(self.channel_ids_to_brain_area.keys())
            channels.append(data[:, channel_indices])

        excitation_series = np.concatenate(applied_voltages)
        measured_voltages = np.concatenate(channels)
        # Conversion: raw signal (V) → current (A)
        response_series = measured_voltages / conversion_factor

        return excitation_series, response_series

    def get_original_timestamps(self) -> np.ndarray:
        """
        Get the original timestamps from the FSCV data files.

        Returns
        -------
        np.ndarray
            Array of original timestamps.
        """
        times = []
        for file_path in self.source_data["file_paths"]:
            mat = read_mat(file_path)
            if self.data_key not in mat:
                raise KeyError(f"Key '{self.data_key}' not found in {file_path}")
            data = mat[self.data_key]
            times.append(data[:, 0])
        return np.concatenate(times)

    def get_timestamps(self) -> np.ndarray:
        return self._timestamps if self._timestamps is not None else self.get_original_timestamps()

    def set_aligned_timestamps(self, aligned_timestamps):
        self._timestamps = aligned_timestamps

    def set_aligned_starting_time(self, aligned_starting_time: float) -> None:
        self.set_aligned_timestamps(aligned_timestamps=self.get_timestamps() + aligned_starting_time)

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict, conversion_factor: float) -> None:
        """
        Adds the FSCV data to the NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add the data to.
        metadata : dict
            Metadata for the FSCV data.
        conversion_factor : float
            Factor to convert raw signal (V) to current (A).
        """
        excitation_series, response_series = self.read_data(conversion_factor=conversion_factor)
        timestamps = self.get_timestamps()

        excitation_series_metadata = metadata["FSCV"]["FSCVExcitationSeries"]
        excitation_series_obj = FSCVExcitationSeries(
            data=excitation_series,
            timestamps=timestamps,
            **excitation_series_metadata,
        )

        # Create device and electrode group
        device_metadata = metadata["FSCV"]["Device"]
        device = nwbfile.create_device(**device_metadata)
        electrode_group_metadata = metadata["FSCV"]["ElectrodeGroup"]
        electrode_group = nwbfile.create_electrode_group(
            name=electrode_group_metadata["name"],
            description=electrode_group_metadata["description"],
            location=electrode_group_metadata.get("location", "unknown"),
            device=device,
        )

        # Add the electrodes to the NWBFile
        electrode_locations = [self.channel_ids_to_brain_area[ch_idx] for ch_idx in self.channel_ids_to_brain_area]
        num_electrodes = len(electrode_locations)
        if (electrodes := nwbfile.electrodes) is None:
            for electrode_location in electrode_locations:
                nwbfile.add_electrode(group=electrode_group, location=electrode_location)

            fscv_electrodes = nwbfile.create_electrode_table_region(
                region=list(range(num_electrodes)),
                description="FSCV electrodes",
            )
        else:
            properties_to_fill = electrodes.colnames
            null_values_for_rows = dict()
            for property in properties_to_fill:
                if property not in ["group", "location", "group_name", "channel_name"]:
                    null_value = _get_null_value_for_property(
                        property=property,
                        sample_data=electrodes[property][:][0],
                        null_values_for_properties=dict(),
                    )
                    null_values_for_rows[property] = null_value

            for electrode_id, electrode_location in self.channel_ids_to_brain_area.items():
                nwbfile.add_electrode(
                    group=electrode_group,
                    group_name=electrode_group_metadata["name"],
                    channel_name=str(electrode_id),
                    location=electrode_location,
                    **null_values_for_rows,
                    enforce_unique_id=True,
                )
            fscv_electrodes_table = electrodes[:][electrodes[:]["group_name"] == electrode_group_metadata["name"]]
            fscv_electrodes = nwbfile.create_electrode_table_region(
                region=fscv_electrodes_table.reset_index()["id"].values.tolist(),
                description="FSCV electrodes",
            )

        response_series_metadata = metadata["FSCV"]["FSCVResponseSeries"]
        if num_electrodes == 1:
            response_series = response_series.flatten()
        response_series_obj = FSCVResponseSeries(
            data=response_series,
            timestamps=timestamps,
            current_to_voltage_factor=1 / conversion_factor,
            electrodes=fscv_electrodes,
            excitation_series=excitation_series_obj,
            **response_series_metadata,
        )

        nwbfile.add_stimulus(excitation_series_obj)
        nwbfile.add_acquisition(response_series_obj)
