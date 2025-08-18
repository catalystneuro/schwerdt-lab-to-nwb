"""Primary NWBConverter class for this dataset."""

from neuroconv import NWBConverter
from neuroconv.datainterfaces import (
    NeuralynxRecordingInterface,
    PlexonSortingInterface,
)
from neuroconv.utils import DeepDict

from schwerdt_lab_to_nwb.interfaces import BehaviorInterface


class Amjad2025NWBConverter(NWBConverter):
    """Primary conversion class for my extracellular electrophysiology dataset."""

    data_interface_classes = dict(
        Recording=NeuralynxRecordingInterface,
        Sorting=PlexonSortingInterface,
        Behavior=BehaviorInterface,
    )

    def get_metadata(self) -> DeepDict:
        metadata = super().get_metadata()

        # Plexon is an offline sorter, so we should use the session start time from the recording
        if "Sorting" in self.data_interface_objects:
            recording_interface = self.data_interface_objects["Recording"]
            recording_metadata = recording_interface.get_metadata()
            session_start_time = recording_metadata["NWBFile"]["session_start_time"]
            metadata["NWBFile"]["session_start_time"] = session_start_time

        return metadata
