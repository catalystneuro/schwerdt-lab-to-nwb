"""Primary NWBConverter class for this dataset."""

from neuroconv import NWBConverter
from neuroconv.datainterfaces import (
    PhySortingInterface,
    SpikeGLXRecordingInterface,
)

from schwerdt_lab_to_nwb.choi_2025 import Choi2025BehaviorInterface


class Choi2025NWBConverter(NWBConverter):
    """Primary conversion class for my extracellular electrophysiology dataset."""

    data_interface_classes = dict(
        Recording=SpikeGLXRecordingInterface,
        Sorting=PhySortingInterface,
        Behavior=Choi2025BehaviorInterface,
    )
