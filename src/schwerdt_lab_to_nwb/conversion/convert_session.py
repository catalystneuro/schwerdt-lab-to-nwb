from logging import warn
from pathlib import Path
from zoneinfo import ZoneInfo

from natsort import natsorted
from neuroconv.datainterfaces import NeuralynxRecordingInterface, PlexonSortingInterface
from neuroconv.utils import dict_deep_update, load_dict_from_file
from spikeinterface.extractors import NeuralynxRecordingExtractor

from schwerdt_lab_to_nwb.converters import MicroinvasiveProbesNWBConverter
from schwerdt_lab_to_nwb.interfaces import (
    BehaviorInterface,
    EyeTrackingBehaviorInterface,
    FSCVRecordingInterface,
    NlxLfpRecordingInterface,
    TrialAlignedFSCVInterface,
)


def session_to_nwb(
    neuralynx_folder_path: Path | str,
    nwb_folder_path: Path | str,
    metadata_yaml_file_path: Path | str,
    subject_metadata_key: str,
    session_id: str = None,
    raw_fscv_recording_folder_path: Path | str = None,
    fscv_channel_ids_to_brain_area: dict[int, str] | None = None,
    lfp_file_path: Path | str = None,
    lfp_data_key: str = "tr_nlx",
    plexon_file_path: Path | str = None,
    ephys_channel_name_to_brain_area: dict[str, str] | None = None,
    behavior_trlist_file_path: Path | str = None,
    behavior_trlist_key: str = "trlist",
    ttl_code_to_event_name: dict[int, str] | None = None,
    trial_aligned_fscv_file_path: Path | str = None,
    trial_aligned_fscv_key: str = "c8ds_fscv",
    stub_test: bool = False,
    verbose: bool = False,
):
    """
    Convert a single session to NWB format.

    Performs the conversion of extracellular electrophysiology data from Neuralynx format to NWB format.

    Parameters
    ----------
    neuralynx_folder_path : DirectoryPath
        Path to the directory containing the Neuralynx data files (.ncs) for the session.
    nwb_folder_path : DirectoryPath
        The directory path where the converted NWB file will be saved.
        The file will be named 'sub-{subject_id}_ses-{session_id}.nwb'.
    subject_metadata_key : str
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

    session_folder_path = Path(neuralynx_folder_path)
    session_id = session_id or session_folder_path.name
    nwb_folder_path = Path(nwb_folder_path)
    if stub_test:
        nwb_folder_path = nwb_folder_path / "nwb_stub"
    nwb_folder_path.mkdir(parents=True, exist_ok=True)

    data_interfaces = dict()
    conversion_options = dict()

    has_neuralynx = len(list(session_folder_path.glob("*.ncs"))) > 0
    if has_neuralynx:
        # Check available streams
        stream_names, stream_ids = NeuralynxRecordingExtractor.get_streams(
            folder_path=session_folder_path,
            exclude_filename=None,
            strict_gap_mode=False,
        )

        eye_tracking_streams = [stream for stream in stream_names if "100mV" in stream]
        recording_streams = [stream for stream in stream_names if "1mV" in stream]

        if len(recording_streams) == 1:
            stream_name = recording_streams[0]

            # Check segments
            neuralynx_extractor = NeuralynxRecordingExtractor(
                folder_path=session_folder_path,
                stream_name=stream_name,
                strict_gap_mode=False,
            )
            num_detected_segments = neuralynx_extractor.get_num_segments()
            if num_detected_segments == 1:
                recording_interface = NeuralynxRecordingInterface(
                    folder_path=session_folder_path,
                    stream_name=stream_name,
                    es_key="electrical_series",
                )
                data_interfaces.update(dict(Recording=recording_interface))
                conversion_options.update(dict(Recording=dict(stub_test=stub_test)))
            else:
                from schwerdt_lab_to_nwb.interfaces import (
                    NeuralynxConcatenateSegmentRecordingInterface,
                )

                warn(
                    f"Detected {num_detected_segments} segments in Neuralynx data for stream '{stream_name}'. "
                    "Using NeuralynxConcatenateSegmentRecordingInterface for conversion."
                )
                recording_interface = NeuralynxConcatenateSegmentRecordingInterface(
                    folder_path=session_folder_path,
                    stream_name=stream_name,
                    es_key="electrical_series",
                )
                data_interfaces.update(dict(Recording=recording_interface))
                conversion_options.update(dict(Recording=dict(stub_test=stub_test)))

        if len(eye_tracking_streams) == 1:
            stream_name = eye_tracking_streams[0]
            eye_tracking_interface = EyeTrackingBehaviorInterface(
                folder_path=session_folder_path,
                stream_name=stream_name,
            )
            data_interfaces.update(dict(EyeTracking=eye_tracking_interface))
            conversion_options.update(dict(EyeTracking=dict(stub_test=stub_test)))

    # Add FSCV Recording
    if raw_fscv_recording_folder_path is not None:
        raw_fscv_recording_folder_path = Path(raw_fscv_recording_folder_path)
        assert (
            fscv_channel_ids_to_brain_area is not None
        ), "'fscv_channel_ids_to_brain_area' must be provided when 'raw_fscv_recording_folder_path' is specified."
        channel_indices = list(fscv_channel_ids_to_brain_area.keys())
        if len(channel_indices) == 1:
            brain_area = fscv_channel_ids_to_brain_area[channel_indices[0]]

            file_paths = natsorted(raw_fscv_recording_folder_path.glob(f"*{brain_area}*.mat"))
            if len(file_paths):
                fscv_recording_interface = FSCVRecordingInterface(
                    file_paths=file_paths,
                    channel_ids_to_brain_area=fscv_channel_ids_to_brain_area,
                    data_key="recordedData",
                )
                data_interfaces.update(dict(FSCVRecording=fscv_recording_interface))
                conversion_options.update(dict(FSCVRecording=dict(conversion_factor=1e9 / 4.99e6, stub_test=stub_test)))
            else:
                warn(
                    f"No raw FSCV recording files found for brain area '{brain_area}' in '{raw_fscv_recording_folder_path}'."
                )

    # Add LFP
    if lfp_file_path is not None:
        lfp_interface = NlxLfpRecordingInterface(
            file_path=lfp_file_path,
            trials_key=lfp_data_key,
            sampling_frequency=1000.0,
        )
        data_interfaces.update(dict(LFP=lfp_interface))
        conversion_options.update(dict(LFP=dict(stub_test=stub_test)))

    # Add Sorting
    if plexon_file_path is not None:
        plexon_interface = PlexonSortingInterface(file_path=plexon_file_path)
        data_interfaces.update(dict(Sorting=plexon_interface))
        conversion_options.update(
            dict(Sorting=dict(stub_test=stub_test, units_description="Spike-sorted units from Plexon Offline Sorter."))
        )

    # Add Behavior
    if behavior_trlist_file_path is not None:
        behavior_interface = BehaviorInterface(file_path=behavior_trlist_file_path, trials_key=behavior_trlist_key)
        data_interfaces.update(dict(Behavior=behavior_interface))
        if ttl_code_to_event_name is not None:
            conversion_options.update(dict(Behavior=dict(event_mapping=ttl_code_to_event_name, stub_test=stub_test)))
        else:
            raise ValueError(
                f"TTL code to event name mapping is required when '{behavior_trlist_file_path}' is specified. "
                "Please provide this mapping using the 'event_mapping' argument."
            )

    # Add TrialAlignedFSCV
    if trial_aligned_fscv_file_path is not None:
        trial_aligned_fscv_interface = TrialAlignedFSCVInterface(
            file_path=trial_aligned_fscv_file_path,
            trials_key=trial_aligned_fscv_key,
            sampling_frequency=10.0,
        )
        data_interfaces.update(dict(TrialAlignedFSCV=trial_aligned_fscv_interface))

    converter = MicroinvasiveProbesNWBConverter(data_interfaces=data_interfaces, verbose=verbose)

    # Fetch metadata from converter
    metadata = converter.get_metadata()
    session_start_time = metadata["NWBFile"]["session_start_time"]

    # Add datetime to conversion
    session_start_time = session_start_time.replace(tzinfo=ZoneInfo("America/New_York"))
    metadata["NWBFile"].update(session_start_time=session_start_time)

    # Update default metadata with the editable in the corresponding yaml file
    editable_metadata = load_dict_from_file(metadata_yaml_file_path)
    metadata = dict_deep_update(metadata, editable_metadata)

    # Update the ecephys metadata
    metadata["Ecephys"] = editable_metadata["Ecephys"]
    if "LFP" not in data_interfaces:
        # pop LFP metadata if no LFP interface
        metadata["Ecephys"].pop("lfp_series")

    subject_metadata = metadata["Subjects"].get(subject_metadata_key, None)
    if subject_metadata is None:
        raise ValueError(
            f"Subject '{subject_metadata_key}' is not found in the metadata. "
            f"Please add an entry for this subject to '{metadata_yaml_file_path}' under the 'Subjects' section."
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

    print(f"Converted NWB file saved to: {nwbfile_path}")
