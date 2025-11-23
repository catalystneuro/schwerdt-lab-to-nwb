# schwerdt-lab-to-nwb
NWB conversion scripts for Schwerdt lab data to the
[Neurodata Without Borders](https://nwb-overview.readthedocs.io/) data format.

This repository contains conversion tools for electrophysiological, fast-scan cyclic voltammetry (FSCV), behavioral,
and eye-tracking data from experiments conducted in the Schwerdt lab.

## Installation

To use this conversion package, you'll need to install it directly from GitHub. This approach allows you to access the
latest features and modify the source code if needed to adapt to your specific experimental requirements.

### Prerequisites

Before installation, ensure you have the following tools installed:
- `git` ([installation instructions](https://github.com/git-guides/install-git))
- `conda` ([installation instructions](https://docs.conda.io/en/latest/miniconda.html)) - recommended for managing dependencies

### Installation steps

From a terminal (note that conda should install one in your system) you can do the following:

```
git clone https://github.com/catalystneuro/schwerdt-lab-to-nwb
cd schwerdt-lab-to-nwb
conda env create --file make_env.yml
conda activate schwerdt_lab_to_nwb_env
```

This creates a [conda environment](https://docs.conda.io/projects/conda/en/latest/user-guide/concepts/environments.html) which isolates the conversion code from your system libraries.
We recommend that you run all your conversion related tasks and analysis from the created environment in order to
minimize issues related to package dependencies.

Alternatively, if you want to avoid conda altogether (for example if you use another virtual environment tool) you
can install the repository with the following commands using only pip:

```
git clone https://github.com/catalystneuro/schwerdt-lab-to-nwb
cd schwerdt-lab-to-nwb
pip install --editable .
```
Note: both of the methods above install the repository in [editable mode](https://pip.pypa.io/en/stable/cli/pip_install/#editable-installs).
The dependencies for this environment are stored in the dependencies section of the `pyproject.toml` file.

## Data Organization and Conversion Process

The conversion notes in `src/schwerdt_lab_to_nwb/amjad_2025/conversion_notes.md` and in
`src/schwerdt_lab_to_nwb/choi_2025/conversion_notes.md` provide detailed information about the data organization and
conversion process.

## Usage

Once you have installed the package, you can run any of the conversion scripts in a notebook or a python file:

### Converting multiple sessions

To convert multiple sessions, you can create a YAML file that lists the sessions to be converted along with their specific parameters.
See `src/schwerdt_lab_to_nwb/choi_2025/session_map.yaml` or `src/schwerdt_lab_to_nwb/amjad_2025/session_map.yaml`
for an example of how to structure this file:

```yaml
Sessions:
  - neuralynx_folder_path: "/Users/weian/data/Schwerdt/additional data/data_microinvasiveProbes_manuscript/Monkey P"
    subject_metadata_key: "Monkey P"
    plexon_file_path: "/Users/weian/data/Schwerdt/additional data/data_microinvasiveProbes_manuscript/Monkey P/csc12.plx"
    ephys_channel_name_to_brain_area: {CSC12: "cl3"}
    session_id: 08132018
```

```python
from pathlib import Path
from schwerdt_lab_to_nwb.conversion import dataset_to_nwb, get_session_to_nwb_kwargs_per_session

# Define the session map and metadata file paths
yaml_file_path = Path(__file__) / "src/schwerdt_lab_to_nwb/amjad_2025/session_map.yml"
metadata_yaml_file_path = Path(__file__) / "src/schwerdt_lab_to_nwb/amjad_2025/metadata.yml"
# Define the output directory for NWB files
output_dir_path = Path("/Users/weian/data/Schwerdt/nwbfiles/data_microinvasiveProbes_manuscript/")

# Get session and metadata configurations from the YAML files
session_to_nwb_kwargs_per_session = get_session_to_nwb_kwargs_per_session(
        session_map_path=yaml_file_path,
        metadata_yaml_file_path=metadata_yaml_file_path,
)

verbose = True
stub_test = False  # Set to True for quick testing with limited data

dataset_to_nwb(
        session_to_nwb_kwargs_per_session=session_to_nwb_kwargs_per_session,
        output_dir_path=output_dir_path,
        verbose=verbose,
        stub_test=stub_test,
)

```

### Converting a single session to NWB

You can also convert a single session by specifying the required parameters directly in your script:

```python
from pathlib import Path
from schwerdt_lab_to_nwb.conversion import session_to_nwb

# Define your data paths

# Required data paths
# Path to the directory containing the Neuralynx data files (.ncs) for the session.
neuralynx_folder_path = "/Users/weian/data/Schwerdt/additional data/data_chamber_manuscript/09272024"
# The directory path where the converted NWB file will be saved. The file will be named 'sub-{subject_id}_ses-{session_id}.nwb'.
nwb_folder_path = "/Users/weian/data/Schwerdt/nwb_output/"
# The subject key to look for in the metadata under 'Subjects' section (e.g. "Monkey T", "Monkey P").
subject_metadata_key = "Monkey T"
# Path to the YAML file containing metadata for the NWB file.
metadata_file_path = Path(__file__) / "src/schwerdt_lab_to_nwb/choi_2025/metadata.yml"

# Optional data paths
# Path to the folder containing raw FSCV recording .mat files.
raw_fscv_recording_folder_path = "/Users/weian/data/Schwerdt/additional data/data_chamber_manuscript/09272024/raw fscv data with all recorded ch"
# A mapping from FSCV channel IDs (0-based indexing) to brain area names.
fscv_channel_ids_to_brain_area=  {6: "c8ds"}  # 0-based indexing (would be channel 7 in MATLAB)
# Path to the differential LFP signal file (.mat) for the session.
lfp_file_path = "/Users/weian/data/Schwerdt/additional data/data_chamber_manuscript/09272024/tr_nlx_c7b-c5c.mat"
# The key in the LFP .mat file that contains the data array.
lfp_data_key = "tr_nlx"
# Path to the Plexon file (.plx) containing spike data for the session.
plexon_file_path= "/Users/weian/data/Schwerdt/additional data/data_chamber_manuscript/09272024/csc23_100.plx"
# A mapping from electrophysiology channel names to brain area names. If provided, the brain area will be set for each channel in the NWB file.
ephys_channel_name_to_brain_area = {"CSC76": "c5d", "CSC7": "c5c", "CSC47": "c7b",}
# Path to the behavioral trial list file (.mat) for the session.
behavior_trlist_file_path = "/Users/weian/data/Schwerdt/additional data/data_chamber_manuscript/09272024/trlists.mat"
# The key in the behavioral trial list .mat file that contains the trial data.
behavior_trlist_key= "trlist"
# Path to the trial-aligned FSCV data file (.mat) for the session.
trial_aligned_fscv_file_path ="/Users/weian/data/Schwerdt/additional data/data_chamber_manuscript/09272024/09272024_c8ds_fscv.mat"
# The key in the trial-aligned FSCV .mat file that contains the FSCV data.
trial_aligned_fscv_key = "c8ds_fscv"

# Convert the session to NWB
nwbfile = session_to_nwb(
    neuralynx_folder_path=neuralynx_folder_path,
    nwb_folder_path="/Users/weian/data/Schwerdt/nwb_output/",
    subject_metadata_key=subject_metadata_key,
    metadata_yaml_file_path=metadata_file_path,
    raw_fscv_recording_folder_path=raw_fscv_recording_folder_path,
    fscv_channel_ids_to_brain_area=fscv_channel_ids_to_brain_area,
    lfp_file_path=lfp_file_path,
    lfp_data_key=lfp_data_key,
    plexon_file_path=plexon_file_path,
    ephys_channel_name_to_brain_area=ephys_channel_name_to_brain_area,
    behavior_trlist_file_path=behavior_trlist_file_path,
    behavior_trlist_key=behavior_trlist_key,
    trial_aligned_fscv_file_path=trial_aligned_fscv_file_path,
    trial_aligned_fscv_key=trial_aligned_fscv_key,
)
```

### Conversion parameters

#### Required parameters

- `neuralynx_folder_path`: Path to the directory containing the Neuralynx data files (.ncs) for the session.
- `nwb_folder_path`: The directory path where the converted NWB file will be saved
- `subject_metadata_key`: The subject key to look for in the metadata under 'Subjects' section (e.g. "Monkey T", "Monkey P").
- `metadata_yaml_file_path`: Path to the YAML file containing metadata for the NWB file

#### Optional parameters

- `raw_fscv_recording_folder_path`: Path to the folder containing raw FSCV recording .mat files.
- `fscv_channel_ids_to_brain_area`: A mapping from FSCV channel IDs (0-based indexing) to brain area names.
- `lfp_file_path`: Path to the differential LFP signal file (.mat) for the session.
- `lfp_data_key`: The key in the LFP .mat file that contains the data array.
- `plexon_file_path`: Path to the Plexon file (.plx) containing spike data for the session.
- `ephys_channel_name_to_brain_area`: A mapping from electrophysiology channel names to brain area names. If provided, the brain area will be set for each channel in the NWB file.
- `behavior_trlist_file_path`: Path to the behavioral trial list file (.mat) for the session.
- `behavior_trlist_key`: The key in the behavioral trial list .mat file that contains the trial data.
- `trial_aligned_fscv_file_path`: Path to the trial-aligned FSCV data file (.mat) for the session.
- `trial_aligned_fscv_key`: The key in the trial-aligned FSCV .mat file that contains the FSCV data
- `stub_test`: If set to True, only a small subset of the data will be processed for quick testing.
- `verbose`: If set to True, detailed logs will be printed during the conversion process.

## Repository structure
Each conversion is organized in a directory of its own in the `src` directory:

    schwerdt-lab-to-nwb/
    ├── LICENSE
    ├── make_env.yml
    ├── pyproject.toml
    ├── README.md
    └── src
        ├── schwerdt_lab_to_nwb
        │   └── amjad_2025
        │       ├── conversion_notes.md
        │       ├── convert_all_sessions.py
        │       ├── metadata.yaml
        │       ├── session_map.yml
        │       ├── upload_sessions_to_dandi.py
        │       └── __init__.py
        │   ├── choi_2025
        │       ├── conversion_notes.md
        │       ├── convert_all_sessions.py
        │       ├── metadata.yaml
        │       ├── session_map.yml
        │       ├── upload_sessions_to_dandi.py
        │   ├── conversion
        │       ├── __init__.py
        │       ├── convert_session.py
        │       ├── dataset_to_nwb.py
        └── __init__.py

For example, for the conversion `choi_2025` you can find a directory located in `src/schwerdt-lab-to-nwb/choi_2025`.
Inside each conversion directory you can find the following files:

* `conversion_notes.md`: notes and comments concerning this specific conversion.
* `convert_all_sessions.py`: this script defines the function to convert all sessions defined in the `session_map.yml` file.
* `session_map.yml`: a yaml file that defines all sessions to be converted and their specific parameters.
* `metadata.yml`: metadata in yaml format for this specific conversion.
* `upload_sessions_to_dandi.py`: a script to upload all converted sessions to DANDI.

### Key Files

- `conversion/convert_session.py`: Contains the main function `session_to_nwb` that handles the conversion of a single session to NWB format.
- `conversion/dataset_to_nwb.py`: Contains the function `dataset_to_nwb` that manages the conversion of multiple sessions based on a session map.
- `interfaces/`: Contains custom data interfaces for handling specific data types (e.g., FSCV, eye tracking).
- `amjad_2025/` and `choi_2025/`: Contain conversion scripts and metadata specific to different experiments or datasets.
- `tutorials/`: Contains example notebooks demonstrating how to use the conversion tools.
- `utils/`: Contains utility functions for data processing.

## Helpful Definitions

This conversion project is comprised primarily by DataInterfaces, NWBConverters, and conversion scripts.

### DataInterface

In neuroconv, a [DataInterface](https://neuroconv.readthedocs.io/en/main/user_guide/datainterfaces.html) is a class that
specifies the procedure to convert a single data modality to NWB. This is usually accomplished with a single read
operation from a distinct set of files. For example, in this conversion:

Standardized DataInterfaces imported from `neuroconv`:
- **NeuralynxRecordingInterface**: Converts Neuralynx electrophysiology data (.ncs files) to NWB `ElectricalSeries`.
- **PlexonSortingInterface**: Converts Plexon spike sorting data (.plx files) to NWB `Units`.

Custom DataInterfaces defined in `schwerdt_lab_to_nwb/interfaces/`:
- **BehaviorInterface**: Converts behavioral trial data from `.mat` files to NWB trials and events tables.
- **EyeTrackingBehaviorInterface**: Converts eye-tracking data from Neuralynx CSC files to NWB `EyeTracking` container.
- **FSCVRecordingInterface**: Converts raw FSCV recording data from `.mat` files to NWB `FSCVResponseSeries` and `FSCVExcitationSeries` using the `ndx-fscv` extension.
- **NlxLfpRecordingInterface**: Converts differential LFP data from `.mat` files to NWB `ElectricalSeries`.
- **TrialAlignedFSCVInterface**: Converts trial-aligned FSCV data from `.mat` files to NWB `TimeIntervals` table within a processing module.
-
### NWBConverter

In neuroconv, a [NWBConverter](https://neuroconv.readthedocs.io/en/main/user_guide/nwbconverter.html) is a class that
combines many data interfaces and specifies the relationships between them, such as temporal alignment.
The `MicroinvasiveProbesNWBConverter` combines:

- Electrophysiology data:
  - Raw EPhys from `NeuralynxRecordingInterface`, processed LFP from `NlxLfpRecordingInterface`.
  - Spike sorting from `PlexonSortingInterface`.
- FSCV data:
  - Raw FSCV from `FSCVRecordingInterface`.
  - Trial-aligned FSCV from `TrialAlignedFSCVInterface`.
- Behavioral data from `BehaviorInterface`.
- Eye-tracking data from `EyeTrackingBehaviorInterface`.

## Customizing for New Datasets

To create a new conversion or adapt this one for different experimental paradigms:

### 1. Create a New Dataset Directory

Follow the naming convention and create a new directory under `src/schwerdt_lab_to_nwb/`:

```bash
mkdir src/schwerdt_lab_to_nwb/new_experiment_2025
```

### 2. Implement Dataset-Specific Interfaces

Make sure to check NeuroConv documentation to see if your data is already supported at:  https://neuroconv.readthedocs.io/en/stable/conversion_examples_gallery/index.html
If you do not see the format you need, feel free to [request it](https://github.com/catalystneuro/neuroconv/issues/new?assignees=&labels=enhancement,data+interfaces&template=format_request.yml) or
[Build a DataInterface](https://neuroconv.readthedocs.io/en/stable/developer_guide/build_data_interface.html#build-data-interface).

Create custom interfaces inheriting from `BaseDataInterface`:

```python
from neuroconv import BaseDataInterface

class CustomSpikeSortingInterface(BaseDataInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def add_to_nwbfile(self, nwbfile, metadata, **kwargs):
        # Custom processing logic
        super().add_to_nwbfile(nwbfile, metadata, **kwargs)
```

### 3. Create an NWBConverter Class

Combine all interfaces for your dataset:

```python
from neuroconv import NWBConverter
from neuroconv.datainterfaces import ExternalVideoInterface
from .custom_interfaces import CustomSpikeSortingInterface  # Import your custom interfaces

class NewExperimentNWBConverter(NWBConverter):
    data_interface_classes = dict(
        SpikeSorting=CustomSpikeSortingInterface,
        Video=ExternalVideoInterface,
        # Add other interfaces as needed
    )
```

### 4. Write Conversion Scripts

Create scripts for single sessions and batch processing following the established patterns.

### 5. Create Metadata Files

Develop YAML metadata files with dataset-specific experimental parameters:

```yaml
NWBFile:
  experiment_description: "Description of your new experiment"
  institution: "Your Institution"
  lab: "Your Lab"

Subject:
  species: "Mus musculus"
  # Add subject-specific metadata

# Add other experimental metadata
```

Each conversion should be self-contained within its directory and follow the established patterns for consistency and maintainability.

### Getting Help

For issues specific to this conversion:
1. Check the `conversion_notes.md` file in the conversion directory
2. Review the metadata YAML files for parameter examples
3. Examine the conversion scripts for usage patterns

For general neuroconv issues:
- Visit the [neuroconv documentation](https://neuroconv.readthedocs.io/)
- Check the [neuroconv GitHub repository](https://github.com/catalystneuro/neuroconv)

## Citation

If you use this conversion in your research, please cite:

- The original experimental work (add appropriate citation)
- [NeuroConv](https://github.com/catalystneuro/neuroconv)
- [NWB](https://www.nwb.org/)

## License

This project is licensed under the terms specified in the LICENSE file.
