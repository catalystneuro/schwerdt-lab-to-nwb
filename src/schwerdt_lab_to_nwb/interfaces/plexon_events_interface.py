import numpy as np
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools import get_module
from pydantic import FilePath
from pynwb import NWBFile


class PlexonEventsInterface(BaseDataInterface):
    """
    Add the strobed event codes stored in a Plexon .plx file as an AnnotatedEventsTable.

    Used for the Monkey P session, whose task events are only in the .plx file (the same codes and times as the
    Neuralynx events file on Zenodo, session126_events.mat). No code map is available for this session, so each
    code is labelled by its value.
    """

    keywords = ("behavior",)

    def __init__(self, file_path: FilePath, verbose: bool = False):
        super().__init__(file_path=file_path)
        self.verbose = verbose
        self._starting_time = 0.0

    def set_aligned_starting_time(self, aligned_starting_time: float) -> None:
        """Shift the event times in the file by this time in seconds to place them on the session clock."""
        self._starting_time = aligned_starting_time

    def read_events(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the event times (s, on the .plx clock) and the event codes of the strobed event channel."""
        from neo.rawio import PlexonRawIO

        reader = PlexonRawIO(filename=str(self.source_data["file_path"]))
        reader.parse_header()
        if reader.event_channels_count() != 1:
            raise ValueError(f"Expected one event channel in {self.source_data['file_path']}.")
        timestamps, _, labels = reader.get_event_timestamps(block_index=0, seg_index=0, event_channel_index=0)
        times = reader.rescale_event_timestamp(timestamps, dtype="float64", event_channel_index=0)
        return times, labels.astype(int)

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict, event_codes_to_skip: tuple[int, ...] = (0,)) -> None:
        from ndx_events import AnnotatedEventsTable

        times, codes = self.read_events()
        times = times + self._starting_time

        annotated_events_metadata = metadata["Events"]["AnnotatedEventsTable"]
        annotated_events = AnnotatedEventsTable(
            name=annotated_events_metadata["name"],
            description=annotated_events_metadata["description"],
        )
        for code in np.unique(codes):
            if code in event_codes_to_skip:
                continue
            annotated_events.add_event_type(
                label=f"TTL code {code}",
                event_description=f"The event times for code {code}. The code map for this session is not available.",
                event_times=np.sort(times[codes == code]).tolist(),
                check_ragged=False,
            )

        events_module = get_module(nwbfile, name="events", description="Contains processed event data.")
        events_module.add(annotated_events)
