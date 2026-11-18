"""Tests for the fixes of the reproduction findings in issues #30 and #31."""

import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from pynwb import NWBHDF5IO
from pynwb.misc import Units
from pynwb.testing.mock.file import mock_NWBFile
from scipy.io import savemat
from spikeinterface.core import NumpySorting

from schwerdt_lab_to_nwb.converters import MicroinvasiveProbesNWBConverter
from schwerdt_lab_to_nwb.interfaces import NlxLfpRecordingInterface, WaveformInterface
from schwerdt_lab_to_nwb.interfaces.trial_aligned_fscv_interface import (
    get_trial_indices_with_data,
)
from schwerdt_lab_to_nwb.utils import (
    drop_spikes_before,
    get_fscv_to_session_time,
    get_neuralynx_record_samples,
    get_neuralynx_sample_times,
    get_neuralynx_starting_time,
    get_sorted_plexon_sorting,
    get_unique_sorted_event_times,
)

SESSION_START = datetime.datetime(2024, 9, 27, 8, 49, 52, tzinfo=ZoneInfo("America/New_York"))
# 'recording_opened' as a wall-clock-as-UTC epoch, the encoding of the Neuralynx and trlist timestamps
SESSION_START_EPOCH = datetime.datetime(2024, 9, 27, 8, 49, 52, tzinfo=datetime.timezone.utc).timestamp()


def test_neuralynx_starting_time_of_acquisition_clock_timestamps():
    # Monkey P (2018): the first record is at 6800.666 s on the clock of the acquisition software, not an epoch
    neuralynx_extractor = SimpleNamespace(neo_reader=SimpleNamespace(global_t_start=6800.666))
    starting_time = get_neuralynx_starting_time(
        neuralynx_extractor=neuralynx_extractor, session_start_time=SESSION_START
    )
    assert starting_time == 6800.666


def _eventsfscv(fscv_start: float, fscv_to_neuralynx, num_scans: int = 601) -> np.ndarray:
    table = np.zeros((num_scans, 20))
    table[:, 0] = fscv_start + 0.1 * np.arange(num_scans)
    table[:, 3] = fscv_to_neuralynx(table[:, 0])
    return table


def test_fscv_clock_is_mapped_through_the_scan_timestamps():
    # FSCV time 0 is 3236.62 s into the session and the FSCV clock runs 10 ppm slow, as in 09272024
    slope, offset = 1.0000102, 3236.62

    def fscv_to_neuralynx(fscv_time):
        return SESSION_START_EPOCH + offset + slope * fscv_time

    eventsfscv = [_eventsfscv(start, fscv_to_neuralynx) for start in (1388.4, 1401.5, 10000.0)]
    # The last trial is cut by the end of the FSCV recording and padded with rows of FSCV time 0
    truncated = _eventsfscv(19650.0, fscv_to_neuralynx, num_scans=900)
    truncated[300:, 0] = 0.0
    eventsfscv.append(truncated)

    fitted_slope, fitted_offset = get_fscv_to_session_time(eventsfscv=eventsfscv, session_start_time=SESSION_START)
    assert fitted_slope == pytest.approx(slope, abs=1e-9)
    assert fitted_offset == pytest.approx(offset, abs=1e-3)


def test_events_of_overlapping_trial_windows_are_stored_once_and_sorted():
    # Two overlapping trial windows list the events at 12.0 and 13.0 twice; the second window starts earlier
    event_times = [np.array([12.0, 10.0, 13.0]), np.array([9.0, 12.0, 13.0, 15.0])]
    event_codes = [np.array([128, 9, 101]), np.array([9, 128, 101, 128])]
    times_per_code = get_unique_sorted_event_times(event_times_per_trial=event_times, event_codes_per_trial=event_codes)
    np.testing.assert_array_equal(times_per_code[128], [12.0, 15.0])
    np.testing.assert_array_equal(times_per_code[9], [9.0, 10.0])
    np.testing.assert_array_equal(times_per_code[101], [13.0])


def test_plexon_units_are_selected_by_channel_and_sorted():
    spike_trains = {0: np.array([30, 10, 20]), 1: np.array([5, 6]), 2: np.array([1])}
    sorting = NumpySorting.from_unit_dict(units_dict_list=[spike_trains], sampling_frequency=1e6)
    sorting.neo_reader = SimpleNamespace(
        header=dict(
            spike_channels=[
                dict(name="csc12_100", id="ch33#0"),
                dict(name="csc12_100", id="ch33#1"),
                dict(name="csc5_100", id="ch42#0"),
            ]
        )
    )
    sorting.block_index = 0

    selected = get_sorted_plexon_sorting(sorting_extractor=sorting, channel_names=["csc12_100"])
    assert list(selected.unit_ids) == [0, 1]
    assert list(selected.get_property("unit_name")) == ["ch33#0", "ch33#1"]
    np.testing.assert_array_equal(selected.get_unit_spike_train(unit_id=0), [10, 20, 30])


def test_plexon_spikes_before_the_recording_are_dropped():
    # Monkey P: the recording starts at 6800.666 s, and 7 spikes of unit #0 have times below 0.02 s,
    # 3 of them repeated
    fs = 30000.0
    spike_trains = {
        0: np.round(np.array([0.0005, 0.0005, 0.017, 6800.7, 6801.0]) * fs).astype(int),
        1: np.round(np.array([6800.75, 6802.0]) * fs).astype(int),
    }
    sorting = NumpySorting.from_unit_dict(units_dict_list=[spike_trains], sampling_frequency=fs)
    sorting.set_property(key="unit_name", values=["ch33#0", "ch33#1"])
    sorting.neo_reader = "reader"
    sorting.block_index = 0

    kept, num_dropped = drop_spikes_before(sorting=sorting, start_time=6800.666)
    assert num_dropped == 3
    np.testing.assert_array_equal(kept.get_unit_spike_train(unit_id=0) / fs, [6800.7, 6801.0])
    np.testing.assert_array_equal(kept.get_unit_spike_train(unit_id=1), spike_trains[1])
    assert list(kept.get_property("unit_name")) == ["ch33#0", "ch33#1"]
    assert kept.neo_reader == "reader"


def test_lfp_trial_windows_are_joined_without_close_timestamps(tmp_path, monkeypatch):
    fs = 1000.0
    num_samples = 60_000
    # 60 s windows around each midpoint: overlapping windows off the common sample grid, then a window that starts
    # one sample after the previous one ends
    trial_midpoints = [100.0, 113.0004, 126.0007, 186.0007 + 1 / fs]
    lfp_per_trial = [np.full(num_samples, float(i)) for i in range(len(trial_midpoints))]
    interface = NlxLfpRecordingInterface.__new__(NlxLfpRecordingInterface)
    interface.source_data = dict(sampling_frequency=fs)
    monkeypatch.setattr(interface, "read_data", lambda: lfp_per_trial)

    timestamps, signal = interface.reconstruct_continuous_signal_from_trials(trial_start_times=trial_midpoints)
    assert np.diff(timestamps).min() >= 0.5 / fs
    # The last window directly follows the previous one, so none of its samples are dropped
    assert np.sum(signal == 3.0) == num_samples


def test_lfp_gaps_between_trial_windows_are_counted(monkeypatch):
    fs = 1000.0
    # The second 60 s window starts 10 s after the first one ends
    lfp_per_trial = [np.zeros(60_000), np.ones(60_000)]
    interface = NlxLfpRecordingInterface.__new__(NlxLfpRecordingInterface)
    interface.source_data = dict(sampling_frequency=fs)
    monkeypatch.setattr(interface, "read_data", lambda: lfp_per_trial)

    _, signal = interface.reconstruct_continuous_signal_from_trials(trial_start_times=[100.0, 170.0])
    assert interface._num_gap_samples == np.isnan(signal).sum() > 0


def test_thresholded_waveforms_are_in_volts_and_spikes_sorted(tmp_path):
    rows = np.array(
        [
            # spike time, unit id, waveform (uV)
            [0.0005, -1, -40.0, -60.0],
            [2.0, 1, -50.0, 10.0],
            [1.5, -1, -45.0, 5.0],
            [1.0, 1, -30.0, 20.0],
        ]
    )
    file_path = tmp_path / "spikes.mat"
    savemat(file_path, dict(csc12_100=rows))
    interface = WaveformInterface(file_path=file_path, spikes_data_key="csc12_100", sampling_frequency=30000.0)
    interface.set_first_sample_time(0.5)

    nwbfile = mock_NWBFile()
    device = nwbfile.create_device(name="device_ecephys")
    group = nwbfile.create_electrode_group(name="ElectrodeGroup", description="", location="striatum", device=device)
    nwbfile.add_electrode(group=group, location="cl3")
    interface.add_to_nwbfile(nwbfile=nwbfile, metadata=None, recording_site="cl3")
    units = nwbfile.processing["ecephys"]["thresholded_units"].to_dataframe()

    poor = units[units["unit_name"] == "-1"].iloc[0]
    np.testing.assert_array_equal(poor["spike_times"], [1.5])
    unit = units[units["unit_name"] == "1"].iloc[0]
    np.testing.assert_array_equal(unit["spike_times"], [1.0, 2.0])
    np.testing.assert_allclose(np.asarray(unit["waveforms"])[:, :, 0], [[-30e-6, 20e-6], [-50e-6, 10e-6]])
    assert (
        "1 spikes with times before the first sample" in nwbfile.processing["ecephys"]["thresholded_units"].description
    )


def test_trials_with_trial_aligned_fscv_data():
    # 09132024: only the first half of the trials have trial-aligned FSCV data
    da = [np.zeros(601), np.zeros(601), np.array([]), np.array([])]
    assert get_trial_indices_with_data(da) == [0, 1]


def test_neuralynx_sample_times_follow_record_timestamps_across_gaps(tmp_path):
    from schwerdt_lab_to_nwb.utils.utils import NCS_HEADER_SIZE, NCS_RECORD_DTYPE

    # Monkey P (2018, 30 kHz): a short record followed by a 9.8 ms jump, and records 1 ppm slower than nominal
    records = np.zeros(4, dtype=NCS_RECORD_DTYPE)
    records["sampling_frequency"] = 30000
    records["num_valid_samples"] = [512, 100, 512, 512]
    records["samples"][1, :100] = np.arange(100)
    records["samples"][1, 100:] = -1  # not valid
    records["samples"][2, :3] = [2000, 2001, 2002]
    record_start_times = np.array([0.0, 512, 612, 1124]) / 30000 * (1 + 1e-6)
    record_start_times[2:] += 0.0098
    records["timestamp"] = 6800_665_780 + np.round(record_start_times * 1e6).astype(np.uint64)
    file_path = tmp_path / "csc12.ncs"
    with open(file_path, "wb") as file:
        file.write(b"\x00" * NCS_HEADER_SIZE)
        file.write(records.tobytes())

    neuralynx_extractor = SimpleNamespace(
        get_property=lambda key: np.array(["CSC12"]),
        neo_reader=SimpleNamespace(ncs_filenames={("CSC12", "11"): str(file_path)}),
    )
    times = get_neuralynx_sample_times(neuralynx_extractor=neuralynx_extractor)
    assert len(times) == 1636

    # The samples are the valid samples of each record, in record order, so each keeps its record's time
    traces = get_neuralynx_record_samples(neuralynx_extractor=neuralynx_extractor)
    assert traces.shape == (1636, 1)
    np.testing.assert_array_equal(traces[512:612, 0], np.arange(100))
    np.testing.assert_array_equal(traces[612:615, 0], [2000, 2001, 2002])
    first_samples = np.array([0, 512, 612, 1124])
    np.testing.assert_allclose(times[first_samples], np.round(record_start_times * 1e6) / 1e6, atol=1e-9)
    assert times[611] == pytest.approx(times[512] + 99 / 30000)


def test_units_tables_have_the_sample_period_as_resolution(tmp_path, monkeypatch):
    from neuroconv import ConverterPipe

    def add_units_tables(self, nwbfile, metadata=None, conversion_options=None):
        nwbfile.units = Units(name="units", description="sorted units")
        module = nwbfile.create_processing_module(name="ecephys", description="processed ecephys")
        module.add(Units(name="thresholded_units", description="thresholded spikes"))

    monkeypatch.setattr(ConverterPipe, "add_to_nwbfile", add_units_tables)
    converter = MicroinvasiveProbesNWBConverter.__new__(MicroinvasiveProbesNWBConverter)
    recording_extractor = SimpleNamespace(get_sampling_frequency=lambda: 30000.0)
    converter.data_interface_objects = dict(Recording=SimpleNamespace(recording_extractor=recording_extractor))

    nwbfile = mock_NWBFile()
    converter.add_to_nwbfile(nwbfile=nwbfile)
    nwbfile.units.add_unit(spike_times=[1.0, 2.0])
    nwbfile.processing["ecephys"]["thresholded_units"].add_unit(spike_times=[1.0, 2.0])

    # ndx-events replaces the PyNWB mapper that writes the resolution, so check the written file
    nwbfile_path = tmp_path / "units.nwb"
    with NWBHDF5IO(nwbfile_path, mode="w") as io:
        io.write(nwbfile)
    with NWBHDF5IO(nwbfile_path, mode="r") as io:
        read_nwbfile = io.read()
        assert read_nwbfile.units.resolution == 1 / 30000.0
        assert read_nwbfile.processing["ecephys"]["thresholded_units"].resolution == 1 / 30000.0


def test_trials_and_events_describe_windows_missing_trials_and_reward_codes(monkeypatch):
    from schwerdt_lab_to_nwb.interfaces import BehaviorInterface

    # Two listed trials; the window of the first also holds the start of an earlier trial that is not in the list
    trial_starts = SESSION_START_EPOCH + np.array([100.0, 115.0])
    earlier_start = SESSION_START_EPOCH + 85.0
    trials_data = dict(
        ts=trial_starts,
        type=["initial cue display", "initial cue display"],
        NlxEventTS=[
            np.array([earlier_start, trial_starts[0], trial_starts[0] + 0.001, trial_starts[1]]),
            np.array([trial_starts[0], trial_starts[0] + 0.001, trial_starts[1]]),
        ],
        NlxEventTTL=[np.array([128, 128, 41, 128]), np.array([128, 41, 128])],
    )
    interface = BehaviorInterface.__new__(BehaviorInterface)
    monkeypatch.setattr(interface, "read_data", lambda: trials_data)
    interface._aligned_start_times = None

    nwbfile = mock_NWBFile(session_start_time=SESSION_START)
    metadata = dict(
        NWBFile=dict(session_start_time=SESSION_START),
        Events=dict(
            AnnotatedEventsTable=dict(name="events_table", description="Task events."),
            event_descriptions={41: "Every rewarded trial with this code got the big reward."},
        ),
    )
    interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, event_mapping={128: "start", 41: "condition 1"})

    assert len(nwbfile.trials) == 2
    assert "consecutive windows overlap" in nwbfile.trials.description
    assert "1 of the 3 trial start events have no row (at 85.00 s)" in nwbfile.trials.description
    events = nwbfile.processing["events"]["events_table"].to_dataframe().set_index("label")
    assert events.loc["condition 1", "event_description"].endswith("got the big reward.")
    assert events.loc["start", "event_description"] == "The event times for code 128."


def test_events_with_code_0_are_kept(monkeypatch):
    from schwerdt_lab_to_nwb.interfaces import BehaviorInterface

    trial_start = SESSION_START_EPOCH + 100.0
    trials_data = dict(
        ts=np.array([trial_start]),
        type=["initial cue display"],
        NlxEventTS=[trial_start + np.array([0.0, 0.05, 1.0, 1.05])],
        NlxEventTTL=[np.array([128, 0, 41, 0])],
    )
    interface = BehaviorInterface.__new__(BehaviorInterface)
    monkeypatch.setattr(interface, "read_data", lambda: trials_data)

    nwbfile = mock_NWBFile(session_start_time=SESSION_START)
    metadata = dict(
        NWBFile=dict(session_start_time=SESSION_START),
        Events=dict(AnnotatedEventsTable=dict(name="events_table", description="Task events.")),
    )
    interface.add_events_to_nwbfile(nwbfile=nwbfile, metadata=metadata, event_mapping={128: "start"})

    events_table = nwbfile.processing["events"]["events_table"]
    assert events_table.description == "Task events."
    assert list(events_table["label"][:]) == ["TTL code 0", "TTL code 41", "start"]
    assert len(events_table["event_times"][0]) == 2


def test_plexon_events_table_describes_the_plexon_codes(monkeypatch):
    from schwerdt_lab_to_nwb.interfaces import PlexonEventsInterface

    interface = PlexonEventsInterface.__new__(PlexonEventsInterface)
    interface.source_data = dict(file_path="csc12.plx")
    interface._starting_time = 0.0
    monkeypatch.setattr(interface, "read_events", lambda: (np.array([1.0, 1.05, 2.0]), np.array([9, 0, 18])))

    nwbfile = mock_NWBFile(session_start_time=SESSION_START)
    # The description of the trial list sessions does not apply to the Plexon codes
    metadata = dict(Events=dict(AnnotatedEventsTable=dict(name="events_table", description="Named by the event map.")))
    interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)

    events_table = nwbfile.processing["events"]["events_table"]
    assert "csc12.plx" in events_table.description
    assert "event map" not in events_table.description
    assert list(events_table["label"][:]) == ["TTL code 0", "TTL code 9", "TTL code 18"]


def test_eye_tracking_is_written_in_volts_as_x_and_y():
    from spikeinterface.core import NumpyRecording

    from schwerdt_lab_to_nwb.interfaces import EyeTrackingBehaviorInterface

    # The channels are stored as (y, x) in ADC counts
    counts = np.array([[100, -200], [300, -400]], dtype="int16")
    recording = NumpyRecording(traces_list=[counts], sampling_frequency=32000.0, channel_ids=["CSC145", "CSC146"])
    recording.set_channel_gains(3.0517578125)
    recording.set_channel_offsets(0.0)
    interface = EyeTrackingBehaviorInterface.__new__(EyeTrackingBehaviorInterface)
    interface.extractor_eye_tracking = recording

    nwbfile = mock_NWBFile(session_start_time=SESSION_START)
    metadata = dict(
        Behavior=dict(
            EyeTracking=dict(
                Device=dict(name="device_ecephys"),
                SpatialSeries=dict(name="eye_tracking_series", description="Eye position.", unit="volts"),
            )
        )
    )
    interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)

    spatial_series = nwbfile.acquisition["EyeTracking"].spatial_series["eye_tracking_series"]
    assert spatial_series.unit == "volts"
    np.testing.assert_allclose(spatial_series.data[:] * spatial_series.conversion, counts[:, [1, 0]] * 3.0517578125e-6)
