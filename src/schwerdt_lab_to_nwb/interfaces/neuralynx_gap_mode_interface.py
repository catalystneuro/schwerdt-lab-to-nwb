import json

import numpy as np
from neuroconv.datainterfaces.ecephys.baserecordingextractorinterface import (
    BaseRecordingExtractorInterface,
)
from neuroconv.datainterfaces.ecephys.neuralynx.neuralynxdatainterface import (
    extract_neo_header_metadata,
)
from neuroconv.utils import dict_deep_update
from pydantic import DirectoryPath
from spikeinterface import ConcatenateSegmentRecording
from spikeinterface.core import NumpyRecording
from spikeinterface.extractors import NeuralynxRecordingExtractor

from schwerdt_lab_to_nwb.utils import (
    get_neuralynx_record_samples,
    get_neuralynx_sample_times,
)


class NeuralynxConcatenateSegmentRecordingInterface(BaseRecordingExtractorInterface):
    """Primary data interface for converting over-segmented Neuralynx data. Uses
    :py:class:`~spikeinterface.extractors.NeuralynxRecordingExtractor`."""

    display_name = "Neuralynx Recording"
    associated_suffixes = (".ncs", ".nse", ".ntt", ".nse", ".nev")
    info = "Interface for Neuralynx recording data."

    Extractor = ConcatenateSegmentRecording

    @classmethod
    def get_stream_names(cls, folder_path: DirectoryPath) -> list[str]:
        from spikeinterface.extractors import NeuralynxRecordingExtractor

        stream_names, _ = NeuralynxRecordingExtractor.get_streams(folder_path=folder_path)
        return stream_names

    @classmethod
    def get_source_schema(cls) -> dict:
        source_schema = super().get_source_schema()
        source_schema["properties"]["folder_path"][
            "description"
        ] = 'Path to Neuralynx directory containing ".ncs", ".nse", ".ntt", ".nse", or ".nev" files.'
        return source_schema

    def _source_data_to_extractor_kwargs(self, source_data: dict) -> dict:
        extractor_kwargs = source_data.copy()
        extractor_kwargs["all_annotations"] = True

        return extractor_kwargs

    def __init__(
        self,
        folder_path: DirectoryPath,
        stream_name: str | None = None,
        verbose: bool = False,
        es_key: str = "ElectricalSeries",
    ):
        """
        Initialize reading of Neuralynx ephys recording.

        Parameters
        ----------
        folder_path: FolderPathType
            Path to Neuralynx directory.
        stream_name : str, optional
            The name of the recording stream to load; only required if there is more than one stream detected.
            Call `NeuralynxRecordingInterface.get_stream_names(folder_path=...)` to see what streams are available.
        verbose : bool, default: False
        es_key : str, default: "ElectricalSeries"
        """
        neuralynx_extractor = NeuralynxRecordingExtractor(
            folder_path=folder_path, stream_name=stream_name, strict_gap_mode=False
        )
        self.neuralynx_extractor = (
            neuralynx_extractor  # keep a reference to the original extractor for metadata extraction
        )
        num_detected_segments = neuralynx_extractor.get_num_segments()
        if num_detected_segments == 1:
            raise ValueError(
                "The provided Neuralynx data does not appear to be over-segmented. Use NeuralynxRecordingInterface instead."
            )

        # The samples and their times are read from the .ncs records: neo's non-strict gap mode places the samples
        # between groups of short records out of order, and counting at the nominal rate from the start of each
        # segment drifts from the record timestamps by several milliseconds over the 2018 recording
        traces = get_neuralynx_record_samples(neuralynx_extractor=neuralynx_extractor)
        sample_times = get_neuralynx_sample_times(neuralynx_extractor=neuralynx_extractor)
        if len(sample_times) != len(traces) or len(traces) != neuralynx_extractor.get_total_samples():
            raise ValueError("The number of samples in the .ncs records does not match the recording.")
        if not np.all(np.diff(sample_times) > 0):
            raise ValueError("The .ncs record timestamps are not strictly increasing.")

        recording = NumpyRecording(
            traces_list=[traces],
            sampling_frequency=neuralynx_extractor.get_sampling_frequency(),
            channel_ids=neuralynx_extractor.channel_ids,
        )
        for key in neuralynx_extractor.get_property_keys():
            recording.set_property(key, neuralynx_extractor.get_property(key))
        recording.set_times(sample_times, segment_index=0)
        self.recording_extractor = recording

        # the rest is copied from NeuralynxRecordingInterface
        property_names = self.recording_extractor.get_property_keys()
        if "channel_name" not in property_names and "channel_names" in property_names:
            channel_names = self.recording_extractor.get_property("channel_names")
            self.recording_extractor.set_property("channel_name", channel_names)
            self.recording_extractor.delete_property("channel_names")

        self.verbose = verbose
        self.es_key = es_key
        self._number_of_segments = self.recording_extractor.get_num_segments()

        # convert properties of object dtype (e.g. datetime) and bool as these are not supported by nwb
        for key in self.recording_extractor.get_property_keys():
            value = self.recording_extractor.get_property(key)
            if value.dtype == object or value.dtype == np.bool_:
                self.recording_extractor.set_property(key, np.asarray(value, dtype=str))

    def get_metadata(self) -> dict:
        neo_metadata = extract_neo_header_metadata(self.neuralynx_extractor.neo_reader)

        # remove filter related entries already covered by `add_recording_extractor_properties`
        neo_metadata = {k: v for k, v in neo_metadata.items() if not k.lower().startswith("dsp")}

        # map Neuralynx metadata to NWB
        nwb_metadata = {"NWBFile": {}, "Ecephys": {"Device": []}}
        neuralynx_device = None
        if "SessionUUID" in neo_metadata:
            # note: SessionUUID can not be used as 'identifier' as this requires uuid4
            nwb_metadata["NWBFile"]["session_id"] = neo_metadata.pop("SessionUUID")
        if "recording_opened" in neo_metadata:
            nwb_metadata["NWBFile"]["session_start_time"] = neo_metadata.pop("recording_opened")
        if "AcquisitionSystem" in neo_metadata:
            neuralynx_device = {"name": neo_metadata.pop("AcquisitionSystem")}
        elif "HardwareSubSystemType" in neo_metadata:
            neuralynx_device = {"name": neo_metadata.pop("HardwareSubSystemType")}
        if neuralynx_device is not None:
            if "ApplicationName" in neo_metadata or "ApplicationVersion" in neo_metadata:
                name = neo_metadata.pop("ApplicationName", "")
                version = str(neo_metadata.pop("ApplicationVersion", ""))
                neuralynx_device["description"] = f"{name} {version}"
            nwb_metadata["Ecephys"]["Device"].append(neuralynx_device)

        neo_metadata = {k: str(v) for k, v in neo_metadata.items()}
        nwb_metadata["NWBFile"]["notes"] = json.dumps(neo_metadata, ensure_ascii=True)

        return dict_deep_update(super().get_metadata(), nwb_metadata)
