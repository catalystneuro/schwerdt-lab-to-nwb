from neuroconv import BaseDataInterface
from neuroconv.utils import DeepDict
from pydantic import DirectoryPath
from pynwb import NWBFile
from pynwb.behavior import EyeTracking, SpatialSeries
from spikeinterface.extractors import NeuralynxRecordingExtractor


class EyeTrackingBehaviorInterface(BaseDataInterface):
    """
    Data interface for adding eye-tracking data from Neuralynx files to an NWBFile.
    This interface reads eye-tracking data (e.g., timestamps, gaze positions) from Neuralynx files and adds them to the NWBFile.
    """

    keywords = ("behavior", "eye-tracking")

    def __init__(self, folder_path: DirectoryPath, verbose: bool = False):
        """
        Initialize the EyeTrackingBehaviorInterface.

        Parameters
        ----------
        folder_path : DirectoryPath
            Path to the folder containing Neuralynx eye-tracking files.
        verbose : bool, optional
            Whether to print verbose output during processing.
        """
        super().__init__(folder_path=folder_path)
        self.verbose = verbose
        self.extractor_eye_tracking = NeuralynxRecordingExtractor(folder_path=self.source_data["folder_path"])

    def get_metadata(self) -> DeepDict:
        from neuroconv.datainterfaces.ecephys.neuralynx.neuralynxdatainterface import (
            extract_neo_header_metadata,
        )

        metadata = super().get_metadata()

        neo_metadata = extract_neo_header_metadata(self.extractor_eye_tracking.neo_reader)

        # map Neuralynx metadata to NWB
        neuralynx_device = None
        if "SessionUUID" in neo_metadata:
            metadata["NWBFile"]["session_id"] = neo_metadata.pop("SessionUUID")
        if "recording_opened" in neo_metadata:
            metadata["NWBFile"]["session_start_time"] = neo_metadata.pop("recording_opened")
        if "AcquisitionSystem" in neo_metadata:
            neuralynx_device = {"name": neo_metadata.pop("AcquisitionSystem")}
        elif "HardwareSubSystemType" in neo_metadata:
            neuralynx_device = {"name": neo_metadata.pop("HardwareSubSystemType")}
        if neuralynx_device is not None:
            if "ApplicationName" in neo_metadata or "ApplicationVersion" in neo_metadata:
                name = neo_metadata.pop("ApplicationName", "")
                version = str(neo_metadata.pop("ApplicationVersion", ""))
                neuralynx_device["description"] = f"{name} {version}"
            metadata["Behavior"]["EyeTracking"]["Device"] = neuralynx_device

        metadata["Behavior"]["EyeTracking"].update(
            SpatialSeries=dict(
                name="eye_tracking_series", description="Eye tracking data as recorded by Neuralynx system."
            )
        )

        return metadata

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict | None, stub_test: bool = False) -> None:
        device_metadata = metadata["Behavior"]["EyeTracking"]["Device"]
        device_name = device_metadata["name"]
        if device_name not in nwbfile.devices:
            nwbfile.create_device(**device_metadata)

        rate = self.extractor_eye_tracking.get_sampling_frequency()
        end_frame = None if not stub_test else int(rate * 100)  # 100 seconds
        data = self.extractor_eye_tracking.get_traces(end_frame=end_frame)  # Maybe y, x originally
        # if traces are (N, 2) with (y, x), swap to (x, y)
        if data.ndim == 2 and data.shape[1] == 2:
            data = data[:, [1, 0]]
        spatial_series_metadata = metadata["Behavior"]["EyeTracking"]["SpatialSeries"]
        spatial_series = SpatialSeries(
            name=spatial_series_metadata["name"],
            data=data,
            description=spatial_series_metadata["description"],
            starting_time=self.extractor_eye_tracking.get_start_time(),
            rate=rate,
        )

        eye_tracking = EyeTracking(spatial_series=[spatial_series])

        nwbfile.add_acquisition(eye_tracking)
