import traceback
from pathlib import Path
from pprint import pformat

from neuroconv.utils import load_dict_from_file
from tqdm import tqdm

from schwerdt_lab_to_nwb.conversion import session_to_nwb
from schwerdt_lab_to_nwb.utils import get_event_codes_from_trlist_file_path


def dataset_to_nwb(
    *,
    output_dir_path: str | Path,
    session_to_nwb_kwargs_per_session=list[dict],
    verbose: bool = True,
    stub_test: bool = False,
):
    """Convert the entire dataset to NWB ."""
    output_dir_path = Path(output_dir_path)
    if not output_dir_path.exists():
        output_dir_path.mkdir(parents=True, exist_ok=True)

    # Sequential conversion over discovered sessions
    for session_to_nwb_kwargs in tqdm(session_to_nwb_kwargs_per_session, desc="Converting sessions"):
        # assign output dir and verbosity
        session_to_nwb_kwargs.update(
            nwb_folder_path=output_dir_path,
            verbose=verbose,
            stub_test=stub_test,
        )

        try:
            session_to_nwb(**session_to_nwb_kwargs)
        except Exception:
            session_name = Path(session_to_nwb_kwargs["neuralynx_folder_path"]).name
            exception_file_path = output_dir_path / f"ERROR_{session_name}.txt"
            with open(exception_file_path, mode="w") as f:
                f.write(f"session_to_nwb_kwargs: \n {pformat(session_to_nwb_kwargs)}\n\n")
                f.write(traceback.format_exc())


def get_session_to_nwb_kwargs_per_session(
    *,
    session_map_path: str | Path,
    metadata_yaml_file_path: str | Path,
) -> list[dict]:
    """Get session_to_nwb kwargs for all sessions in the dataset.

    Parameters
    ----------
    session_map_path : Union[str, Path]
        Path to session map YAML file.
    metadata_yaml_file_path : Union[str, Path]
        Path to metadata YAML file.
    Returns
    -------
    session_to_nwb_kwargs_per_session : list of dict
        List of keyword arguments to pass to session_to_nwb for each session.
    """
    session_dirs = []

    session_map = load_dict_from_file(session_map_path)
    sessions_to_convert = session_map.get("Sessions", []) if isinstance(session_map, dict) else []
    for session_kwargs in sessions_to_convert:

        ttl_code_to_event_name = None
        if (trlist_file_path := session_kwargs.get("behavior_trlist_file_path", None)) is not None:
            ttl_code_to_event_name = get_event_codes_from_trlist_file_path(
                file_path=trlist_file_path,
                event_code_rename_map={128: "intended trial start"},
                event_codes_to_skip=[0, 9, 40, 41],
            )

        # resolve session folder path; allow relative paths (relative to data_dir_path)
        neuralynx_folder_path = session_kwargs.get("neuralynx_folder_path")
        session_folder_path = Path(neuralynx_folder_path)
        subject_metadata_key = session_kwargs.pop("subject_metadata_key", session_folder_path.parent.name)
        session_id = session_kwargs.pop("session_id", session_folder_path.name)

        fscv_channel_ids_to_brain_area = session_kwargs.pop("fscv_channel_ids_to_brain_area", None)
        ephys_channel_name_to_brain_area = session_kwargs.pop("ephys_channel_name_to_brain_area", None)
        session_kwargs = dict(
            **session_kwargs,
            subject_metadata_key=subject_metadata_key,
            session_id=session_id,
            ttl_code_to_event_name=ttl_code_to_event_name,
            fscv_channel_ids_to_brain_area=fscv_channel_ids_to_brain_area,
            ephys_channel_name_to_brain_area=ephys_channel_name_to_brain_area,
            metadata_yaml_file_path=metadata_yaml_file_path,
        )
        session_dirs.append(session_kwargs)

    return session_dirs
