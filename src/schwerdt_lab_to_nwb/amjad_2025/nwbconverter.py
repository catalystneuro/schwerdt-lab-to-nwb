"""Primary NWBConverter class for this dataset."""

import numpy as np
from neuroconv import NWBConverter
from neuroconv.datainterfaces import (
    NeuralynxRecordingInterface,
    PlexonSortingInterface,
)

from schwerdt_lab_to_nwb.interfaces import BehaviorInterface, NlxLfpRecordingInterface


class Amjad2025NWBConverter(NWBConverter):
    """Primary conversion class for my extracellular electrophysiology dataset."""

    trial_start_code = 128  # TTL code indicating the start of a trial

    data_interface_classes = dict(
        Recording=NeuralynxRecordingInterface,
        Sorting=PlexonSortingInterface,
        Behavior=BehaviorInterface,
        LFP=NlxLfpRecordingInterface,
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
        num_trials = len(trials_data.get("ts", []))
        trial_start_indices = [
            np.where(trials_data["NlxEventTTL"][trial_index] == self.trial_start_code)[0]
            for trial_index in range(num_trials)
        ]
        trial_start_times = [
            trials_data["NlxEventTS"][trial_index][start_indices[0]]
            for trial_index, start_indices in enumerate(trial_start_indices)
            if len(start_indices) > 0
        ]

        if not trial_start_times:
            raise ValueError("No trial start times found.")

        if conversion_options and conversion_options.get("Behavior", {}).get("stub_test", False):
            trial_start_times = trial_start_times[:100]

        behavior_interface.set_aligned_trial_start_times(aligned_start_times=trial_start_times)
