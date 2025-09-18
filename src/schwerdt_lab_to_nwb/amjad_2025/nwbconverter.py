"""Primary NWBConverter class for this dataset."""

from neuroconv import NWBConverter
from neuroconv.datainterfaces import (
    NeuralynxRecordingInterface,
    PlexonSortingInterface,
)

from schwerdt_lab_to_nwb.interfaces import (
    BehaviorInterface,
    FSCVRecordingInterface,
    NlxLfpRecordingInterface,
)


class Amjad2025NWBConverter(NWBConverter):
    """Primary conversion class for my extracellular electrophysiology dataset."""

    data_interface_classes = dict(
        Recording=NeuralynxRecordingInterface,
        FSCVRecording=FSCVRecordingInterface,
        Sorting=PlexonSortingInterface,
        Behavior=BehaviorInterface,
        LFP=NlxLfpRecordingInterface,
    )
