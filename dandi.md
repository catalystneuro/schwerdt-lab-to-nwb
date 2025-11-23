# DANDI archive instructions

## Setup

1. Create a DANDI account at https://dandiarchive.org/
2. Install the DANDI client in your local Python environment (already gets installed in the conda environment of this repo):

```
pip install dandi
```

3. Export your DANDI API token as an environment variable (copy it from DANDI archive website).

If you're on Linux / MacOS:

```
export DANDI_API_KEY=personal-key-value
```

If you're on Windows:
```
set DANDI_API_KEY=personal-key-value
```

## Upload data

Each conversion directory contains a script `upload_sessions_to_dandi.py` that can be used to upload the converted NWB files to DANDI.
Make sure to modify the script to point to the correct folder containing the NWB files before running it.
You can then run the upload script as follows:

```bash
cd src/schwerdt_lab_to_nwb/amjad_2025
python upload_sessions_to_dandi.py
```

You can also upload files manually using the DANDI web interface by following the instructions at https://docs.dandiarchive.org/user-guide-sharing/uploading-data/.
