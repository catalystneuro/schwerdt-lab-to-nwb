import os
from pathlib import Path

from neuroconv.tools.data_transfers import automatic_dandi_upload

if __name__ == "__main__":
    if "DANDI_API_KEY" not in os.environ:
        raise EnvironmentError("DANDI_API_KEY environment variable is not set.")

    nwb_folder_path = Path("/Users/weian/data/Schwerdt/nwbfiles/data_chamber_manuscript/")

    dandiset_id = "001627"
    dandiset_folder_path = nwb_folder_path / "dandiset"
    dandiset_folder_path.mkdir(parents=True, exist_ok=True)

    automatic_dandi_upload(
        dandiset_id=dandiset_id,
        nwb_folder_path=nwb_folder_path,
        dandiset_folder_path=dandiset_folder_path,
    )
