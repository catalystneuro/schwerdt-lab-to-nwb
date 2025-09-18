from typing import List

import numpy as np
from ndx_fscv import FSCVExcitationSeries, FSCVResponseSeries
from neuroconv import BaseDataInterface
from neuroconv.tools.spikeinterface.spikeinterface import _get_null_value_for_property
from neuroconv.utils import get_schema_from_hdmf_class
from pydantic import FilePath
from pymatreader import read_mat
from pynwb import NWBFile
from pynwb.device import Device
from pynwb.ecephys import ElectrodeGroup


class FSCVRecordingInterface(BaseDataInterface):

    def __init__(
        self,
        file_paths: List[FilePath],
        channel_indices: List[int] = None,
        data_key: str = "recordedData",
    ):
        """
        Data interface for reading FSCV data files.

        Parameters
        ----------
        file_paths : List[FilePath]
            List of paths to the FSCV data files.
        channel_indices : List[int], optional
            List of channel indices to read from the data files. If None, all channels are read. Default is None.
        data_key : str
            Key in the .mat file dictionary that contains the FSCV data. Default is "recordedData".
        """
        super().__init__(file_paths=file_paths)
        self.channel_indices = channel_indices if channel_indices is not None else []
        self.data_key = data_key

    def get_metadata_schema(self) -> dict:
        metadata_schema = super().get_metadata_schema()
        # Add FSCV series schemas under "FSCV"
        metadata_schema["properties"]["FSCV"] = dict(
            type="object",
            required=["Device", "ElectrodeGroup", "FSCVResponseSeries", "FSCVExcitationSeries"],
            properties=dict(
                Device=dict(type="array", minItems=1, items={"$ref": "#/properties/Ecephys/definitions/Device"}),
                ElectrodeGroup=dict(
                    type="array", minItems=1, items={"$ref": "#/properties/Ecephys/definitions/ElectrodeGroup"}
                ),
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
            Device=[dict(name="device_fscv", description="FSCV recording")],
            ElectrodeGroup=[
                dict(
                    name="FSCVElectrodeGroup",
                    description="The group of FSCV electrodes.",
                    device="device_fscv",
                )
            ],
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
            channels.append(data[:, self.channel_indices])

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

    def add_to_nwbfile(
        self, nwbfile: NWBFile, metadata: dict | None, electrode_locations: List[str], conversion_factor: float
    ) -> None:
        """
        Adds the FSCV data to the NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add the data to.
        metadata : dict, optional
            Metadata for the FSCV data.
        electrode_locations : List[str]
            The recording site of each electrode.
        conversion_factor : float
            Factor to convert raw signal (V) to current (A).
        """
        excitation_series, response_series = self.read_data(conversion_factor=conversion_factor)
        timestamps = self.get_original_timestamps()

        excitation_series_metadata = metadata["FSCV"]["FSCVExcitationSeries"]
        excitation_series_obj = FSCVExcitationSeries(
            data=excitation_series,
            timestamps=timestamps,
            **excitation_series_metadata,
        )

        # Create device and electrode group
        device_metadata = metadata["FSCV"]["Device"][0]
        device = nwbfile.create_device(**device_metadata)
        electrode_group_metadata = metadata["FSCV"]["ElectrodeGroup"][0]
        electrode_group = nwbfile.create_electrode_group(
            name=electrode_group_metadata["name"],
            description=electrode_group_metadata["description"],
            location=electrode_group_metadata.get("location", "unknown"),
            device=device,
        )

        # Add the electrodes to the NWBFile
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
            new_electrode_ids = [
                f"CH{ch_idx + 1}" for ch_idx in self.channel_indices
            ]  # todo: whether to use matlab based indexing here
            for electrode_id, electrode_location in zip(new_electrode_ids, electrode_locations):
                nwbfile.add_electrode(
                    group=electrode_group,
                    group_name=electrode_group_metadata["name"],
                    channel_name=electrode_id,
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
