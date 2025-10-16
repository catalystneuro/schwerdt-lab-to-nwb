"""Primary NWBConverter class for this dataset."""

import numpy as np
from neuroconv import NWBConverter
from neuroconv.datainterfaces import (
    NeuralynxRecordingInterface,
    PlexonSortingInterface,
)

from schwerdt_lab_to_nwb.interfaces import BehaviorInterface, NlxLfpRecordingInterface
from schwerdt_lab_to_nwb.utils import convert_unix_timestamps_to_datetime


class Amjad2025NWBConverter(NWBConverter):
    """Primary conversion class for my extracellular electrophysiology dataset."""

    trial_start_code = 128  # TTL code indicating the start of a trial

    data_interface_classes = dict(
        Recording=NeuralynxRecordingInterface,
        Sorting=PlexonSortingInterface,
        LFP=NlxLfpRecordingInterface,
        Behavior=BehaviorInterface,
        TrialAlignedFSCV=TrialAlignedFSCVInterface,
    )

    def temporally_align_data_interfaces(self, metadata: dict | None = None, conversion_options: dict | None = None):
        """
        Align the trial start times based on TTL trial start code from the Behavior data interface.
        The aligned trial start times are set in the Behavior interface for downstream use.
        """

        if "Behavior" not in self.data_interface_objects:
            return

        behavior_interface = self.data_interface_objects["Behavior"]

        trials_data = behavior_interface.read_data()

        unaligned_trial_start_times = trials_data["ts"]
        unaligned_trial_start_times_dt = convert_unix_timestamps_to_datetime(unaligned_trial_start_times)

        aligned_trial_start_times = []
        for trial_index, reference_trial_start_time in enumerate(unaligned_trial_start_times_dt):
            trial_start_indices = np.where(trials_data["NlxEventTTL"][trial_index] == self.trial_start_code)[0]
            trial_start_times = trials_data["NlxEventTS"][trial_index][trial_start_indices]
            trial_start_times_ttl = convert_unix_timestamps_to_datetime(trial_start_times)

            aligned_trial_start = min(trial_start_times_ttl, key=lambda dt: abs(dt - reference_trial_start_time))
            aligned_trial_start_times.append(aligned_trial_start)

        if conversion_options and conversion_options.get("Behavior", {}).get("stub_test", False):
            aligned_trial_start_times = aligned_trial_start_times[:100]

        behavior_interface.set_aligned_trial_start_times(aligned_start_times=aligned_trial_start_times)

        if "LFP" in self.data_interface_objects:
            conversion_options["LFP"].update({"trial_start_times": aligned_trial_start_times})
