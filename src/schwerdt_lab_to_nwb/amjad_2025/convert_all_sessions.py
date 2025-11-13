from pathlib import Path

from schwerdt_lab_to_nwb.conversion import (
    dataset_to_nwb,
    get_session_to_nwb_kwargs_per_session,
)

if __name__ == "__main__":
    # Parameters for conversion

    yaml_file_path = Path(__file__).parent / "session_map.yaml"
    metadata_yaml_file_path = Path(__file__).parent / "metadata.yaml"
    output_dir_path = Path("/Users/weian/data/Schwerdt/nwbfiles/data_microinvasiveProbes_manuscript/")

    verbose = True
    stub_test = False  # Set to True for quick testing with limited data

    session_to_nwb_kwargs_per_session = get_session_to_nwb_kwargs_per_session(
        session_map_path=yaml_file_path,
        metadata_yaml_file_path=metadata_yaml_file_path,
    )

    dataset_to_nwb(
        session_to_nwb_kwargs_per_session=session_to_nwb_kwargs_per_session,
        output_dir_path=output_dir_path,
        verbose=verbose,
        stub_test=stub_test,
    )
