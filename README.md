# KBack-artifact

KBack-artifact is a standalone release of the KBack patch backporting workflow. It takes a target kernel tree plus a patch dataset directory, then drives the backporting, build, test, and oracle-validation loop from the `src/` tools.

This repository is intended to be published without the large dataset contents. Keep your dataset, kernel trees, and generated artifacts outside the repository and point the config files at local paths on your machine.

## What is included

- `src/backporting.py`: main entry point for the backport pipeline
- `src/run_oracle_compare_patch.sh`: oracle runner used during validation
- `src/tools/project.py`: project wrapper and agent tools
- `src/example_*.yml`: sample configs for different environments
- `run_all.sh`: batch runner for multiple config directories

## Requirements

- Python 3.10 or newer
- A virtual environment is recommended
- A local target kernel repository
- A local patch dataset directory containing `config.yml`, `build.sh`, `test.sh`, and related artifacts
- Optional: QEMU, ccache, and syzbot-related tooling depending on the validation path you use

## Setup

If you use PDM:

```bash
pdm install
source .venv/bin/activate
```

If you prefer pip:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Start from one of the sample files in `src/` and update the paths and model settings for your environment.

Minimal fields:

```yml
project: linux
project_url: https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/
new_patch: <upstream-fixing-commit>
new_patch_parent: <parent-commit-of-fix>
target_release: <target-kernel-commit>
tag: <syzbot-extid-or-label>
project_dir: /path/to/your/kernel/tree
patch_dataset_dir: /path/to/your/patch_dataset/<sample>/
api_key: <your-api-key>
api_url: https://api.example.com/v1
model: gpt-4o
```

Notes:

- `project_dir` must point to the local kernel tree you want to backport into.
- `patch_dataset_dir` must point to the sample directory that contains the patch artifacts.
- Do not commit real API keys. Leave `api_key` blank in examples and pass secrets through your local environment or private config.
- If you use Azure OpenAI, set `use_azure: true` plus the Azure endpoint/deployment fields.

## Quick Start

Run a single sample:

```bash
cd src
python backporting.py --config example_gpt.yml --debug
```

## Results and artifacts

The pipeline writes its outputs into the dataset sample directory, including:

- `backport.log`
- `patch.txt`
- `need_backport.patch`
- validation and oracle logs under `repro/`

These files are intentionally not tracked in git.

## Validation

The repository includes multiple validation layers:

1. Patch application checks
2. Kernel build checks
3. Testcase execution
4. Oracle validation

The final result should be interpreted against the sample’s ground truth and the oracle output, with the patch’s logic and target location both matching the intended fix.

## Repository notes

- The code assumes local access to the kernel tree and patch dataset paths you configure.
- Example configs are templates only; update them before running.
- If you add new experiments, keep generated logs and datasets out of the repository and update `.gitignore` as needed.
