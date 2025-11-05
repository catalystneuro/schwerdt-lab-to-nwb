"""Primary NWBConverter class for this dataset."""

import numpy as np
from neuroconv import ConverterPipe
from neuroconv.utils import DeepDict

from schwerdt_lab_to_nwb.utils import (
    convert_timestamps_to_relative_timestamps,
    convert_unix_timestamps_to_datetime,
)


class MicroinvasiveProbesNWBConverter(ConverterPipe):
    """
    Custom NWB converter for Schwerdt Lab to convert electrophysiological (Neuralynx),
    fast-scan cyclic voltammetry (custom format), behavioral (custom format), and eye-tracking data (Neuralynx) from
    experiments described in https://doi.org/10.1101/2025.01.30.635139 into NWB format.
    """

    trial_start_code = 128  # TTL code indicating the start of a trial

    def get_metadata(self) -> DeepDict:
        metadata = super().get_metadata()

        # Plexon is an offline sorter, so we should use the session start time from the recording
        if "Sorting" in self.data_interface_objects:
            recording_interface = self.data_interface_objects["Recording"]
            recording_metadata = recording_interface.get_metadata()
            session_start_time = recording_metadata["NWBFile"]["session_start_time"]
            metadata["NWBFile"]["session_start_time"] = session_start_time

        return metadata

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

        session_start_time = None
        if "session_start_time" in metadata["NWBFile"]:
            session_start_time = metadata["NWBFile"]["session_start_time"]

        if "FSCVRecording" in self.data_interface_objects:
            raw_fscv_datainterface = self.data_interface_objects["FSCVRecording"]

            original_timestamps = raw_fscv_datainterface.get_original_timestamps(stub_test=True)

            relative_timestamps = convert_timestamps_to_relative_timestamps(
                timestamps=aligned_trial_start_times,
                start_time=session_start_time,
            )
            unaligned_trial_start_times_from_fscv = trials_data["tsfscv"][: len(aligned_trial_start_times)]
            unaligned_trial_start_times_from_fscv_dt = convert_unix_timestamps_to_datetime(
                unaligned_trial_start_times_from_fscv
            )
            unaligned_relative_trial_start_times_from_fscv = convert_timestamps_to_relative_timestamps(
                timestamps=unaligned_trial_start_times_from_fscv_dt,
                start_time=session_start_time,
            )

            aligned_timestamps = np.interp(
                x=original_timestamps, xp=unaligned_relative_trial_start_times_from_fscv, fp=relative_timestamps
            )
            stub_test = conversion_options["FSCVRecording"].get("stub_test", False)
            raw_fscv_datainterface.set_aligned_starting_time(
                aligned_starting_time=aligned_timestamps[0], stub_test=stub_test
            )
