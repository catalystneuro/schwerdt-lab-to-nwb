"""Primary script to run to convert an entire session for of data using the NWBConverter."""

from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.utils import dict_deep_update, load_dict_from_file

from schwerdt_lab_to_nwb.choi_2025 import Choi2025NWBConverter


def session_to_nwb(
    nwbfile_path: str | Path,
    trial_list_file_path: str | Path,
    stub_test: bool = False,
):
    """
    Convert a session of data to NWB format.

    Parameters
    ----------
    nwbfile_path : str or Path
        The path where the NWB file will be saved.
    trial_list_file_path : str or Path
        The path to the trial list .mat file.
    stub_test : bool, optional
        If True, runs a stub test conversion with minimal data. Default is False.
    """

    nwbfile_path = Path(nwbfile_path)
    nwbfile_path.parent.mkdir(parents=True, exist_ok=True)

    source_data = dict()
    conversion_options = dict()

    # Add Recording
    # source_data.update(dict(Recording=dict()))
    # conversion_options.update(dict(Recording=dict(stub_test=stub_test)))
    #
    # # Add Sorting
    # source_data.update(dict(Sorting=dict()))
    # conversion_options.update(dict(Sorting=dict()))

    # Add Behavior
    source_data.update(dict(Behavior=dict(file_path=trial_list_file_path)))
    conversion_options.update(dict(Behavior=dict()))

    converter = Choi2025NWBConverter(source_data=source_data)

    # Add datetime to conversion
    metadata = converter.get_metadata()
    session_start_time = metadata["NWBFile"]["session_start_time"]
    metadata["NWBFile"].update(session_start_time=session_start_time.replace(tzinfo=ZoneInfo("US/Eastern")))

    # Update default metadata with the editable in the corresponding yaml file
    editable_metadata_path = Path(__file__).parent / "metadata.yaml"
    editable_metadata = load_dict_from_file(editable_metadata_path)
    metadata = dict_deep_update(metadata, editable_metadata)

    # metadata["Subject"]["subject_id"] = "a_subject_id"  # Modify here or in the yaml file

    # Run conversion
    converter.run_conversion(metadata=metadata, nwbfile_path=nwbfile_path, conversion_options=conversion_options)


if __name__ == "__main__":

    # Parameters for conversion
    data_dir_path = Path("/Directory/With/Raw/Formats/")
    trial_list_mat_file_path = Path("/Users/weian/data/Schwerdt/14826579/09262024_trlist.mat")

    nwbfile_path = Path("/Users/weian/data/nwbfiles/choi_2025.nwb")
    stub_test = True

    session_to_nwb(
        nwbfile_path=nwbfile_path,
        trial_list_file_path=trial_list_mat_file_path,
        stub_test=stub_test,
    )
