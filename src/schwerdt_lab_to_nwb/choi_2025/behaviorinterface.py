"""Primary class for converting experiment-specific behavior."""

from datetime import datetime
from pathlib import Path

import numpy as np
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.utils import DeepDict
from pymatreader import read_mat
from pynwb.file import NWBFile


class Choi2025BehaviorInterface(BaseDataInterface):
    """Behavior interface for choi_2025 conversion"""

    keywords = ["behavior", "trials"]

    def __init__(self, file_path: str | Path):
        """Initialize the behavior interface.

        Parameters
        ----------
        file_path : FilePath
            Path to the behavior .mat file.
        """
        self._file = None
        super().__init__(file_path=file_path)

    def read_data(self):
        """Read the data from the .mat file.

        Returns
        -------
        dict
            The data read from the .mat file.
        """
        if self._file is None:
            self._file = read_mat(self.source_data["file_path"])
        return self._file

    def get_metadata(self) -> DeepDict:
        metadata = super().get_metadata()

        if "session_start_time" not in metadata["NWBFile"]:
            # Set a default session start time if not provided
            session_start_time = self.get_trial_timestamps()[0]
            metadata["NWBFile"].update(session_start_time=session_start_time)

        return metadata

    def get_trial_timestamps(self) -> list[datetime]:
        """Get trial timestamps "ts" from the trials data "trlist".

        Returns
        -------
        list[datetime]
            A list of datetime objects representing the trial timestamps.
        """
        trials_data = self.read_data().get("trlist", {})
        if not trials_data:
            raise ValueError(f"Expected 'trlist' key not found in '{self.source_data['file_path']}'.")
        if "ts" not in trials_data:
            raise ValueError(f"Expected 'ts' key not found in '{self.source_data['file_path']}'.")
        timestamps = trials_data["ts"]
        datetime_values = [datetime.fromtimestamp(ts) for ts in timestamps]

        return datetime_values

    def add_trials(self, nwbfile: NWBFile, metadata: dict):
        """Add trials to the NWBFile.

        The trials are extracted from the 'trlist' named struct and added to the NWBFile.

        Parameters
        ----------
        nwbfile : pynwb.NWBFile
            The in-memory object to add the data to.
        """

        session_start_time = metadata["NWBFile"]["session_start_time"]
        trial_timestamps = self.get_trial_timestamps()
        trial_start_times = [
            (dt.replace(tzinfo=session_start_time.tzinfo) - session_start_time).total_seconds()
            for dt in trial_timestamps
        ]
        trial_stop_times = trial_start_times[1:] + [np.nan]

        trials_data = self.read_data().get("trlist", {})
        for trial_index, (start_time, stop_time) in enumerate(zip(trial_start_times, trial_stop_times)):
            # todo: What about "id", "tsfscv" and "eventsfscv" (601x20)
            nwbfile.add_trial(start_time=start_time, stop_time=stop_time, tags=trials_data["type"][trial_index])

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict):
        self.add_trials(nwbfile=nwbfile, metadata=metadata)
