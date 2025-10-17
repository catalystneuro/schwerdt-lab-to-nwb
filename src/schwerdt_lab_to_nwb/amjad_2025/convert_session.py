"""Primary script to run to convert an entire session for of data using the NWBConverter."""

import re
from pathlib import Path
from zoneinfo import ZoneInfo

from natsort import natsorted
from neuroconv.utils import dict_deep_update, load_dict_from_file
from pydantic import DirectoryPath

from schwerdt_lab_to_nwb.amjad_2025 import Amjad2025NWBConverter


def session_to_nwb(
    session_folder_path: DirectoryPath,
    nwb_folder_path: DirectoryPath,
    subject_key: str,
    fscv_channel_ids_to_brain_area: dict[int, str],
    ephys_channel_name_to_brain_area: dict[str, str] | None = None,
    ttl_code_to_event_name: dict[int, str] | None = None,
    stub_test: bool = False,
    verbose: bool = False,
):
    """
    Convert a single session from Amjad 2025 dataset to NWB format.

    Performs the conversion of extracellular electrophysiology data from Neuralynx format to NWB format.

    Parameters
    ----------
    session_folder_path : DirectoryPath
        Path to the directory containing the Neuralynx data files (.ncs) for the session.
    nwb_folder_path : DirectoryPath
        The directory path where the converted NWB file will be saved.
        The file will be named 'sub-{subject_id}_ses-{session_id}.nwb'.
    subject_key : str
        The subject key to look for in the metadata under 'Subjects' section (e.g. "Monkey T", "Monkey P").
    ephys_channel_name_to_brain_area : dict[str, str] | None, optional
        A dictionary mapping EPhys channel names to brain areas.
        If provided, the brain area will be set for each channel in the NWB file.
    fscv_channel_ids_to_brain_area : dict[int, str]
        A dictionary mapping FSCV channel IDs (1-based indexing) to brain areas.
    ttl_code_to_event_name : dict[int, str] | None, optional
        A dictionary mapping TTL event codes to event names.
    stub_test : bool, optional
        Whether to run conversion in stub test mode (not implemented), by default False.
    verbose : bool, optional
        Whether to print progress messages during conversion, by default False.
    """

    session_folder_path = Path(session_folder_path)
    session_id = session_folder_path.name
    nwb_folder_path = Path(nwb_folder_path)
    if stub_test:
        nwb_folder_path = nwb_folder_path / "nwb_stub"
    nwb_folder_path.mkdir(parents=True, exist_ok=True)

    source_data = dict()
    conversion_options = dict()

    # Add Recording
    source_data.update(dict(Recording=dict(folder_path=session_folder_path, es_key="electrical_series")))
    conversion_options.update(dict(Recording=dict(stub_test=stub_test)))

    # Add FSCV Recording
    channel_indices = list(fscv_channel_ids_to_brain_area.keys())
    if len(channel_indices) == 1:
        brain_area = fscv_channel_ids_to_brain_area[channel_indices[0]]
        file_paths = natsorted(session_folder_path.parent.rglob(f"raw*/*{brain_area}*.mat"))[:3]
        if len(file_paths):
            source_data.update(
                dict(
                    FSCVRecording=dict(
                        file_paths=file_paths,
                        channel_ids_to_brain_area=fscv_channel_ids_to_brain_area,
                        data_key="recordedData",
                    )
                )
            )
            conversion_options.update(dict(FSCVRecording=dict(conversion_factor=1e9 / 4.99e6)))

    # Add LFP
    lfp_file_paths = list(session_folder_path.glob("*.mat"))
    lfp_file_paths = [fp for fp in lfp_file_paths if re.match(r"tr_nlx_[a-zA-Z0-9]+-[a-zA-Z0-9]+\.mat$", fp.name)]
    if len(lfp_file_paths) == 1:
        lfp_file_path = lfp_file_paths[0]
        source_data.update(dict(LFP=dict(file_path=lfp_file_path, trials_key="tr_nlx", sampling_frequency=1000.0)))
        conversion_options.update(dict(LFP=dict(stub_test=stub_test)))

    # Add Sorting
    # source_data.update(dict(Sorting=dict()))
    # conversion_options.update(dict(Sorting=dict()))

    # Add Behavior
    trlist_file_paths = list(session_folder_path.glob("*trlist*.mat"))
    if len(trlist_file_paths) == 1:
        trlist_file_path = trlist_file_paths[0]
        source_data.update(dict(Behavior=dict(file_path=trlist_file_path, trials_key="trlist")))
        if ttl_code_to_event_name is not None:
            conversion_options.update(dict(Behavior=dict(event_mapping=ttl_code_to_event_name, stub_test=stub_test)))
        else:
            raise ValueError(
                f"TTL code to event name mapping is required when '{trlist_file_path}' is specified. "
                "Please provide this mapping using the 'event_mapping' argument."
            )
    else:
        raise ValueError(f"Expected one trlist file in '{session_folder_path}', found {len(trlist_file_paths)}.")

    # Add TrialAlignedFSCV
    fscv_file_paths = list(session_folder_path.glob("*fscv*.mat"))
    if len(fscv_file_paths) == 1:
        fscv_file_path = fscv_file_paths[0]
        source_data.update(
            dict(TrialAlignedFSCV=dict(file_path=fscv_file_path, trials_key="c8ds_fscv", sampling_frequency=10.0))
        )

    converter = Amjad2025NWBConverter(source_data=source_data, verbose=verbose)

    # Fetch metadata from converter
    metadata = converter.get_metadata()
    session_start_time = metadata["NWBFile"]["session_start_time"]

    # Add datetime to conversion
    session_start_time = session_start_time.replace(tzinfo=ZoneInfo("America/New_York"))
    metadata["NWBFile"].update(session_start_time=session_start_time)

    # Update default metadata with the editable in the corresponding yaml file
    editable_metadata_path = Path(__file__).parent / "metadata.yaml"
    editable_metadata = load_dict_from_file(editable_metadata_path)
    metadata = dict_deep_update(metadata, editable_metadata)

    # Update the ecephys metadata
    metadata["Ecephys"] = editable_metadata["Ecephys"]

    subject_metadata = metadata["Subjects"].get(subject_key, None)
    if subject_metadata is None:
        raise ValueError(
            f"Subject '{subject_key}' is not found in the metadata. "
            f"Please add an entry for this subject to '{editable_metadata_path}' under the 'Subjects' section."
        )
    metadata["Subject"] = subject_metadata

    metadata["NWBFile"]["session_id"] = session_id

    if ephys_channel_name_to_brain_area is not None:
        # Get the recording extractor from the interface
        recording_interface = converter.data_interface_objects["Recording"]
        recording_extractor = recording_interface.recording_extractor

        channel_ids = recording_interface.channel_ids
        brain_areas = [
            ephys_channel_name_to_brain_area.get(
                recording_extractor.get_channel_property(channel_id=channel_id, key="channel_name"), "unknown"
            )
            for channel_id in channel_ids
        ]

        recording_extractor.set_property(
            key="brain_area",
            values=brain_areas,
            ids=channel_ids,
        )

    subject_id = subject_metadata["subject_id"].replace(" ", "-")
    nwbfile_path = nwb_folder_path / f"sub-{subject_id}_ses-{session_id}.nwb"

    # Run conversion
    converter.run_conversion(
        metadata=metadata,
        nwbfile_path=nwbfile_path,
        conversion_options=conversion_options,
        overwrite=True,
    )


if __name__ == "__main__":

    # Parameters for conversion
    data_dir_path = Path("/Users/weian/data/Schwerdt/additional data/data_chamber_manuscript/09272024")
    output_dir_path = Path("/Users/weian/data/Schwerdt/nwbfiles")
    stub_test = True

    # Define brain areas for each channel using a dictionary
    # TODO extras this from 'recording sites.xlsx' when available
    ephys_channel_name_to_brain_area = {
        "CSC37": "c3bs",
        "CSC38": "c3a",
        "csc23": "c5d",
        "csc12": "cl3",
        "CSC7": "c5c",
        "CSC47": "c7b",
    }

    fscv_channel_ids_to_brain_area = {
        6: "c8ds",  # 0-based indexing (would be channel 7 in MATLAB)
    }

    # TODO: Extract this from file when available
    # 40, 41, 0 missing from trlists.eventmap can be skipped
    event_code_dict = {
        # 9: "start trial", code 9 can be skipped
        12: "frame skipped",
        14: "manual reward",
        18: "end trial",
        21: "feedback",
        23: "value object start",
        24: "central cue end",
        26: "forced forced value cue start",
        27: "forced forced value cue only",
        28: "onedr",
        30: "left cue reward condition 1",
        31: "left cue reward condition 2",
        32: "left cue reward condition 3",
        33: "left cue reward condition 4",
        34: "left cue reward condition 5",
        35: "right cue reward condition 1",
        36: "right cue reward condition 2",
        37: "right cue reward condition 3",
        38: "right cue reward condition 4",
        39: "right cue reward condition 5",
        50: "central cue fixation started",
        51: "value cue fixation started",
        52: "forced trial valuecue fix allowed",
        53: "forced trial valuecue fix started",
        60: "error fixation break target",
        61: "error fixation break initial",
        62: "error fixation never started",
        63: "error fixation break central cue value object",
        64: "error choice never made",
        65: "error choice value initial fix break",
        66: "error choice fixbreak right",
        67: "error choice fixbreak left",
        68: "error forced trial value cue fix never started",
        69: "error forced trial value cue fix break",
        81: "image 1",
        82: "image 2",
        83: "image 3",
        84: "image 4",
        85: "image 5",
        86: "image 6",
        87: "image 7",
        88: "image 8",
        89: "image 9",
        90: "image 10",
        100: "small reward",
        101: "big reward",
        102: "airpuff on",
        103: "airpuff off",
        105: "reward delivery end",
        115: "transient value condition",
        116: "fixed value condition",
        117: "left condition",
        118: "right condition",
        119: "forced trial condition",
        120: "choice trial condition",
        121: "right choice chosen code",
        122: "left choice chosen code",
        128: "trial start",  # or initial central cue start
    }

    session_to_nwb(
        session_folder_path=data_dir_path,
        nwb_folder_path=output_dir_path,
        subject_key="Monkey T",
        ephys_channel_name_to_brain_area=ephys_channel_name_to_brain_area,
        fscv_channel_ids_to_brain_area=fscv_channel_ids_to_brain_area,
        ttl_code_to_event_name=event_code_dict,
        stub_test=stub_test,
    )
