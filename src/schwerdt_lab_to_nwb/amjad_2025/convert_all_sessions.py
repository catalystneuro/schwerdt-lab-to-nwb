"""Primary script to run to convert all sessions in a dataset using session_to_nwb."""

import traceback
from pathlib import Path
from pprint import pformat
from typing import Union

from neuroconv.utils import load_dict_from_file
from tqdm import tqdm

from schwerdt_lab_to_nwb.amjad_2025.convert_session import session_to_nwb


def dataset_to_nwb(
    *,
    yaml_file_path: Union[str, Path],
    output_dir_path: Union[str, Path],
    verbose: bool = True,
    stub_test: bool = False,
):
    """Convert the entire dataset to NWB ."""
    yaml_file_path = Path(yaml_file_path)
    output_dir_path = Path(output_dir_path)
    if not output_dir_path.exists():
        output_dir_path.mkdir(parents=True, exist_ok=True)

    session_to_nwb_kwargs_per_session = get_session_to_nwb_kwargs_per_session(
        session_map_path=yaml_file_path,
    )

    # Sequential conversion over discovered sessions
    for session_to_nwb_kwargs in tqdm(session_to_nwb_kwargs_per_session, desc="Converting sessions"):
        # assign output dir and verbosity
        session_to_nwb_kwargs.update(
            nwb_folder_path=output_dir_path,
            verbose=verbose,
            stub_test=stub_test,
        )

        session_to_nwb(**session_to_nwb_kwargs)
        # # exception file specific to session name
        # session_name = Path(session_to_nwb_kwargs["session_folder_path"]).name
        # exception_file_path = output_dir_path / f"ERROR_{session_name}.txt"
        #
        # safe_session_to_nwb(
        #     session_to_nwb_kwargs=session_to_nwb_kwargs,
        #     exception_file_path=exception_file_path,
        # )


def safe_session_to_nwb(*, session_to_nwb_kwargs: dict, exception_file_path: Union[Path, str]):
    """Convert a session to NWB while handling any errors by recording error messages to the exception_file_path."""
    exception_file_path = Path(exception_file_path)
    try:
        session_to_nwb(**session_to_nwb_kwargs)
    except Exception:
        with open(exception_file_path, mode="w") as f:
            f.write(f"session_to_nwb_kwargs: \n {pformat(session_to_nwb_kwargs)}\n\n")
            f.write(traceback.format_exc())


def get_session_to_nwb_kwargs_per_session(
    *,
    session_map_path: Union[str, Path],
) -> list[dict]:
    """Get session_to_nwb kwargs for all sessions in the dataset.

    Parameters
    ----------
    session_map_path : Union[str, Path]
        Path to session map YAML file.
    Returns
    -------
    session_to_nwb_kwargs_per_session : list of dict
        List of keyword arguments to pass to session_to_nwb for each session.
    """
    session_dirs = []

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

    session_map = load_dict_from_file(session_map_path)
    sessions = session_map.get("Sessions", []) if isinstance(session_map, dict) else []
    for entry in sessions:
        # resolve session folder path; allow relative paths (relative to data_dir_path)
        session_folder_path = entry.get("session_folder_path")
        session_folder_path = Path(session_folder_path)
        subject_key = entry.get("subject_key", session_folder_path.parent.name)
        session_kwargs = dict(
            session_folder_path=session_folder_path,
            subject_key=subject_key,
            session_id=entry.get("session_id", session_folder_path.name),
            fscv_channel_ids_to_brain_area=entry.get("fscv_channel_ids_to_brain_area", None),
            ephys_channel_name_to_brain_area=entry.get("ephys_channel_name_to_brain_area", None),
            ttl_code_to_event_name=event_code_dict,  # TODO get this from trlists.mat
        )
        session_dirs.append(session_kwargs)

    return session_dirs


if __name__ == "__main__":
    # Parameters for conversion
    yaml_file_path = Path(__file__).parent / "session_map.yaml"
    output_dir_path = Path("/Users/weian/data/Schwerdt/nwbfiles/microinvasiveProbes_manuscript/")
    verbose = True
    stub_test = True  # Set to True for quick testing with limited data

    dataset_to_nwb(
        yaml_file_path=yaml_file_path,
        output_dir_path=output_dir_path,
        verbose=verbose,
        stub_test=stub_test,
    )
