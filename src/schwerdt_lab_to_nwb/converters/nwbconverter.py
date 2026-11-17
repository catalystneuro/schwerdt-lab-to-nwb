"""Primary NWBConverter class for this dataset."""

import numpy as np
from hdmf.common import VectorData
from ndx_events.io.events import VectorDataMap as NdxEventsVectorDataMap
from neuroconv import ConverterPipe
from neuroconv.utils import DeepDict
from pynwb import NWBFile, register_map
from pynwb.misc import Units

from schwerdt_lab_to_nwb.utils import (
    convert_unix_timestamps_to_datetime,
    drop_spikes_before,
    get_fscv_to_session_time,
    get_neuralynx_sampling_frequency,
    get_neuralynx_starting_time,
    neuralynx_timestamps_are_epoch,
    set_sampling_frequency,
)


@register_map(VectorData)
class VectorDataMap(NdxEventsVectorDataMap):
    """
    Write the resolution of a Units table to its 'spike_times' column.

    ndx-events 0.2.1 registers its own mapper for VectorData, which replaces the one of PyNWB that writes
    Units.resolution. Without this mapper the resolution is left out of every file written after ndx-events is imported.
    """

    def get_attr_value(self, spec, container, manager):
        if isinstance(container.parent, Units) and container.name == "spike_times" and spec.name == "resolution":
            return container.parent.resolution
        return super().get_attr_value(spec, container, manager)


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

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict | None = None, conversion_options: dict | None = None):
        super().add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, conversion_options=conversion_options)

        # The spikes were detected on the samples of the Neuralynx recording, so two spike times cannot be closer than
        # one sample period of that recording
        if "Recording" in self.data_interface_objects:
            sampling_frequency = self.data_interface_objects["Recording"].recording_extractor.get_sampling_frequency()
            units_tables = [nwbfile.units]
            if "ecephys" in nwbfile.processing:
                units_tables.append(nwbfile.processing["ecephys"].data_interfaces.get("thresholded_units"))
            for units_table in units_tables:
                if units_table is not None:
                    units_table.resolution = 1.0 / sampling_frequency

    def temporally_align_data_interfaces(self, metadata: dict | None = None, conversion_options: dict | None = None):
        """
        Place the Neuralynx data on the session clock and align the trial start times based on the TTL trial
        start code from the Behavior data interface.

        The Neuralynx recording, eye tracking and spike times start at 0 s (the first Neuralynx sample), so they are
        shifted by the time of the first sample relative to the session start time ('recording_opened').
        The sampling frequency of the Neuralynx recording and eye tracking is measured from the .ncs record
        timestamps, which the spike times follow, because the nominal rate in the header drifts from them.
        The aligned trial start times are set in the Behavior interface for downstream use.
        """
        session_start_time = None
        if "session_start_time" in metadata["NWBFile"]:
            session_start_time = metadata["NWBFile"]["session_start_time"]

        if "Recording" in self.data_interface_objects:
            recording_interface = self.data_interface_objects["Recording"]
            # NeuralynxConcatenateSegmentRecordingInterface keeps the original extractor as 'neuralynx_extractor'
            neuralynx_extractor = getattr(
                recording_interface, "neuralynx_extractor", recording_interface.recording_extractor
            )
            neuralynx_starting_time = get_neuralynx_starting_time(
                neuralynx_extractor=neuralynx_extractor, session_start_time=session_start_time
            )
            recording_interface.recording_extractor.shift_times(shift=neuralynx_starting_time)
            # Recordings concatenated from gapped segments already carry a time vector
            if not recording_interface.recording_extractor.has_time_vector():
                set_sampling_frequency(
                    recording=recording_interface.recording_extractor,
                    sampling_frequency=get_neuralynx_sampling_frequency(neuralynx_extractor=neuralynx_extractor),
                )

            # In the 2024 sessions the sorted (Plexon) and thresholded spike times are relative to the first Neuralynx
            # sample. In the 2018 session they are already on the clock of the acquisition software, the session clock.
            spikes_starting_time = (
                neuralynx_starting_time if neuralynx_timestamps_are_epoch(neuralynx_extractor) else 0.0
            )
            if "Sorting" in self.data_interface_objects:
                # Spikes before the first sample cannot be matched to the raw recording
                sorting_interface = self.data_interface_objects["Sorting"]
                sorting_interface.sorting_extractor, num_dropped = drop_spikes_before(
                    sorting=sorting_interface.sorting_extractor,
                    start_time=neuralynx_starting_time - spikes_starting_time,
                )
                sorting_options = (conversion_options or {}).get("Sorting", {})
                if num_dropped and "units_description" in sorting_options:
                    sorting_options["units_description"] += (
                        f" {num_dropped} spikes with times before the first sample of the raw recording were left out;"
                        " they fall at short gaps of the Neuralynx recording, so their times are not session times."
                    )
            for interface_name in ("Sorting", "Waveforms", "PlexonEvents"):
                if interface_name in self.data_interface_objects:
                    self.data_interface_objects[interface_name].set_aligned_starting_time(spikes_starting_time)
            if "Waveforms" in self.data_interface_objects:
                # The same for the thresholded spikes
                self.data_interface_objects["Waveforms"].set_first_sample_time(neuralynx_starting_time)

        if "EyeTracking" in self.data_interface_objects:
            eye_tracking_extractor = self.data_interface_objects["EyeTracking"].extractor_eye_tracking
            eye_tracking_starting_time = get_neuralynx_starting_time(
                neuralynx_extractor=eye_tracking_extractor, session_start_time=session_start_time
            )
            eye_tracking_extractor.shift_times(shift=eye_tracking_starting_time)
            set_sampling_frequency(
                recording=eye_tracking_extractor,
                sampling_frequency=get_neuralynx_sampling_frequency(neuralynx_extractor=eye_tracking_extractor),
            )

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

        if "FSCVRecording" in self.data_interface_objects:
            # The raw FSCV minute files run on their own gapless clock. 'eventsfscv' gives the Neuralynx timestamp of
            # each scan in the trial windows, from which the FSCV clock is mapped to the session clock.
            raw_fscv_datainterface = self.data_interface_objects["FSCVRecording"]
            stub_test = conversion_options["FSCVRecording"].get("stub_test", False)
            slope, offset = get_fscv_to_session_time(
                eventsfscv=trials_data["eventsfscv"], session_start_time=session_start_time
            )
            fscv_times = raw_fscv_datainterface.get_original_timestamps(stub_test=stub_test)
            raw_fscv_datainterface.set_aligned_timestamps(aligned_timestamps=slope * fscv_times + offset)
