"""Primary script to run to convert an entire session for of data using the NWBConverter."""

from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.utils import dict_deep_update, load_dict_from_file
from numpy.testing import assert_array_equal
from pydantic import DirectoryPath

from schwerdt_lab_to_nwb.amjad_2025 import Amjad2025NWBConverter


def session_to_nwb(
    session_folder_path: DirectoryPath,
    nwb_folder_path: DirectoryPath,
    channel_name_to_brain_area: dict[str, str] | None = None,
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
    channel_name_to_brain_area : dict[str, str] | None, optional
        A dictionary mapping channel names to brain areas.
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

    subject_id = str(session_folder_path.parent.name).replace(" ", "-")
    nwbfile_path = nwb_folder_path / f"sub-{subject_id}_ses-{session_id}.nwb"

    source_data = dict()
    conversion_options = dict()

    # Add Recording
    source_data.update(dict(Recording=dict(folder_path=session_folder_path, es_key="electrical_series")))
    conversion_options.update(dict(Recording=dict(stub_test=stub_test)))

    # Add Sorting
    # source_data.update(dict(Sorting=dict()))
    # conversion_options.update(dict(Sorting=dict()))

    # Add Behavior
    trlist_file_paths = list(session_folder_path.glob("*trlist*.mat"))
    if len(trlist_file_paths) == 1:
        trlist_file_path = trlist_file_paths[0]
        source_data.update(dict(Behavior=dict(file_path=trlist_file_path, trials_key="trlist")))
        conversion_options.update(dict(Behavior=dict(stub_test=False)))

    converter = Amjad2025NWBConverter(source_data=source_data, verbose=verbose)

    # Add datetime to conversion
    metadata = converter.get_metadata()
    session_start_time = metadata["NWBFile"]["session_start_time"]
    session_start_time = session_start_time.replace(tzinfo=ZoneInfo("America/New_York"))
    metadata["NWBFile"].update(session_start_time=session_start_time)

    # Update default metadata with the editable in the corresponding yaml file
    editable_metadata_path = Path(__file__).parent / "metadata.yaml"
    editable_metadata = load_dict_from_file(editable_metadata_path)
    metadata = dict_deep_update(metadata, editable_metadata)

    # Update the ecephys metadata
    metadata["Ecephys"] = editable_metadata["Ecephys"]

    metadata["Subject"]["subject_id"] = subject_id
    metadata["NWBFile"]["session_id"] = session_id

    if channel_name_to_brain_area is not None:
        # Get the recording extractor from the interface
        recording_interface = converter.data_interface_objects["Recording"]
        recording_extractor = recording_interface.recording_extractor

        channel_ids = recording_interface.channel_ids
        brain_areas = [
            channel_name_to_brain_area.get(
                recording_extractor.get_channel_property(channel_id=channel_id, key="channel_name"), "unknown"
            )
            for channel_id in channel_ids
        ]

        recording_extractor.set_property(
            key="brain_area",
            values=brain_areas,
            ids=channel_ids,
        )

    # Run conversion
    converter.run_conversion(
        metadata=metadata,
        nwbfile_path=nwbfile_path,
        conversion_options=conversion_options,
        overwrite=True,
    )


if __name__ == "__main__":

    # Parameters for conversion
    data_dir_path = Path("/Users/weian/data/Schwerdt/data_NWB_catalystneuro/Monkey T/09262024")
    output_dir_path = Path("/Users/weian/data/Schwerdt/nwbfiles")
    stub_test = True

    # Define brain areas for each channel using a dictionary
    channel_name_to_brain_area = {
        "CSC37": "c3bs",
        "CSC38": "c3a",
    }

    session_to_nwb(
        session_folder_path=data_dir_path,
        nwb_folder_path=output_dir_path,
        channel_name_to_brain_area=channel_name_to_brain_area,
        stub_test=stub_test,
    )

    # Debugging output TODO: remove before finalizing
    print(f"Conversion completed. NWB file saved to: {output_dir_path}")
    # read the nwb file and check the metadata
    import pandas as pd
    from pynwb import NWBHDF5IO

    pd.set_option("display.max_columns", None)
    nwbfile_path = output_dir_path / "nwb_stub" / "sub-Monkey-T_ses-09262024.nwb"
    with NWBHDF5IO(nwbfile_path, "r") as io:
        nwbfile = io.read()
        assert len(nwbfile.devices) == 1, "Expected one device in the NWB file."
        assert len(nwbfile.electrode_groups) == 1, "Expected one electrode group in the NWB file."
        print(nwbfile.trials[:].head())
        assert "location" in nwbfile.electrodes.colnames, "Expected 'location' column in electrodes table."
        print(nwbfile.electrodes[:].head())
        # check that the brain area is set correctly
        assert_array_equal(
            nwbfile.electrodes["location"][:], ["c3bs", "c3a"]
        ), "Expected brain areas to match the provided dictionary."
