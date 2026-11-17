import datetime
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from spikeinterface.core import NumpyRecording

from schwerdt_lab_to_nwb.utils import (
    convert_unix_timestamps_to_datetime,
    get_neuralynx_sampling_frequency,
    get_neuralynx_starting_time,
    set_sampling_frequency,
)
from schwerdt_lab_to_nwb.utils.utils import NCS_HEADER_SIZE, NCS_RECORD_DTYPE

# First trial start ('ts') and first Neuralynx sample of the 09272024 session (lab wall-clock time encoded as UTC)
FIRST_TRIAL_START = 1727431646.993460
FIRST_NEURALYNX_SAMPLE = 1727431604.10273
# 'recording_opened' from the Neuralynx header of the same session
RECORDING_OPENED = datetime.datetime(2024, 9, 27, 8, 49, 52, tzinfo=ZoneInfo("America/New_York"))


@pytest.fixture
def machine_time_zone(monkeypatch):
    """Run the test as if the conversion machine were in Central Europe (UTC+2 in September)."""
    monkeypatch.setenv("TZ", "Europe/Budapest")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_trial_timestamps_decode_to_lab_wall_clock(machine_time_zone):
    (trial_start,) = convert_unix_timestamps_to_datetime([FIRST_TRIAL_START])
    assert trial_start == datetime.datetime(2024, 9, 27, 10, 7, 26, 993460)


def test_neuralynx_starting_time_is_first_sample_after_recording_opened(machine_time_zone):
    neuralynx_extractor = SimpleNamespace(neo_reader=SimpleNamespace(global_t_start=FIRST_NEURALYNX_SAMPLE))
    starting_time = get_neuralynx_starting_time(
        neuralynx_extractor=neuralynx_extractor, session_start_time=RECORDING_OPENED
    )
    assert starting_time == pytest.approx(4612.10273, abs=1e-6)


def test_neuralynx_sampling_frequency_follows_record_timestamps(tmp_path):
    # The 09272024 session: 32000 Hz in the header, 31999.9624 Hz on the record timestamps
    measured_sampling_frequency = 31999.9624
    num_records = 1000
    records = np.zeros(num_records, dtype=NCS_RECORD_DTYPE)
    records["sampling_frequency"] = 32000
    records["num_valid_samples"] = 512
    record_start_times = np.arange(num_records) * 512 / measured_sampling_frequency
    records["timestamp"] = int(FIRST_NEURALYNX_SAMPLE * 1e6) + np.round(record_start_times * 1e6).astype(np.uint64)
    file_path = tmp_path / "CSC7.ncs"
    with open(file_path, "wb") as file:
        file.write(b"\x00" * NCS_HEADER_SIZE)
        file.write(records.tobytes())

    neuralynx_extractor = SimpleNamespace(
        get_property=lambda key: np.array(["CSC7"]),
        neo_reader=SimpleNamespace(ncs_filenames={("CSC7", "6"): str(file_path)}),
    )
    sampling_frequency = get_neuralynx_sampling_frequency(neuralynx_extractor=neuralynx_extractor)
    assert sampling_frequency == pytest.approx(measured_sampling_frequency, abs=1e-3)

    recording = NumpyRecording(traces_list=[np.zeros((num_records * 512, 1))], sampling_frequency=32000.0)
    set_sampling_frequency(recording=recording, sampling_frequency=sampling_frequency)
    assert recording.get_sampling_frequency() == sampling_frequency
    last_sample = num_records * 512 - 1
    assert recording.sample_index_to_time(last_sample) == pytest.approx(last_sample / measured_sampling_frequency)
