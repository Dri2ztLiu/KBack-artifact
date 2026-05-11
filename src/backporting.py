import argparse
import datetime
import logging
import os
import subprocess
import shutil
import time
from types import SimpleNamespace

import git
import yaml

from agent.invoke_llm import do_backport, initial_agent
from check.usage import get_usage
from tools.logger import add_file_handler, logger
from tools.project import Project


DEFAULT_ORACLE_COMPARE_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "run_oracle_compare_patch.sh",
)


def safe_get_usage(api_key: str, api_url: str):
    try:
        return get_usage(api_key, api_url)
    except Exception as e:
        logger.warning(f"Failed to retrieve usage information: {e}")
        return None


def is_commit_valid(commit_id: str, project_dir: str):
    try:
        repo = git.Repo(project_dir)
        repo.commit(commit_id)
        return True
    except git.exc.BadName:
        logger.error(f"Commit id {commit_id} in .yml is invalid.")
        return False


def rev_parse_commit(commit_id: str, project_dir: str):
    try:
        repo = git.Repo(project_dir)
        return repo.git.rev_parse(commit_id)
    except git.exc.BadName:
        logger.error(f"Commit id {commit_id} in .yml is invalid.")
        return False


def load_yml(file_path: str):
    """
    Load YAML configuration from a file and return the data as a SimpleNamespace object.

    Args:
        file_path (str): The path to the YAML file.

    Returns:
        data (SimpleNamespace): The configuration data stored in a SimpleNamespace object.
    """
    with open(file_path, "r") as file:
        config = yaml.safe_load(file)

    data = SimpleNamespace()
    data.config_file = os.path.abspath(file_path)
    data.project = config.get("project")
    data.project_url = config.get("project_url")
    data.project_dir = config.get("project_dir")
    data.patch_dataset_dir = config.get("patch_dataset_dir")
    data.api_key = config.get("api_key")
    data.api_url = config.get("api_url")
    data.tag = config.get("tag")
    data.model = config.get("model")
    data.fallback_model = config.get("fallback_model", "gpt-5")
    data.model_upgrade_threshold = int(config.get("model_upgrade_threshold", 2))
    data.stable_repo_dir = config.get("stable_repo_dir", "")
    data.oracle_enabled = config.get("oracle_enabled", True)
    data.oracle_compare_script = config.get(
        "oracle_compare_script",
        DEFAULT_ORACLE_COMPARE_SCRIPT,
    )
    data.oracle_timeout_minutes = int(config.get("oracle_timeout_minutes", 120))


    data.use_azure = config.get("use_azure", False)
    data.azure_endpoint = config.get("azure_endpoint", "")
    data.azure_deployment = config.get("azure_deployment", "gpt-4")
    data.azure_api_version = config.get("azure_api_version", "2024-12-01-preview")

    data.new_patch = config.get("new_patch", "")
    if not data.new_patch or not data.new_patch:
        logger.error(
            "Please check your configuration to make sure new_patch is correct!\n"
        )
        exit(1)

    data.new_patch_parent = config.get("new_patch_parent", "")
    if not data.new_patch_parent or not data.new_patch_parent:
        logger.error(
            "Please check your configuration to make sure new_patch_parent is correct!\n"
        )
        exit(1)

    data.target_release = config.get("target_release", "")
    if not data.target_release or not data.target_release:
        logger.error(
            "Please check your configuration to make sure target_release is correct!\n"
        )
        exit(1)

    data.error_message = config.get("error_message", "")
    if not data.error_message:
        logger.warning(
            "Dataset without error info which means that this vulnerability may not have PoC\n"
        )

    data.project_dir = os.path.expanduser(
        data.project_dir if data.project_dir.endswith("/") else data.project_dir + "/"
    )
    data.patch_dataset_dir = os.path.expanduser(
        data.patch_dataset_dir
        if data.patch_dataset_dir.endswith("/")
        else data.patch_dataset_dir + "/"
    )
    if not os.path.isdir(data.project_dir):
        logger.error(f"Project directory does not exist: {data.project_dir}")
        exit(1)
    if not os.path.isdir(data.patch_dataset_dir):
        logger.error(
            f"Patch dataset directory does not exist: {data.patch_dataset_dir}"
        )
        exit(1)

    if (
        not is_commit_valid(data.new_patch, data.project_dir)
        or not is_commit_valid(data.target_release, data.project_dir)
        or not is_commit_valid(data.new_patch_parent, data.project_dir)
    ):
        exit(1)

    data.new_patch = rev_parse_commit(data.new_patch, data.project_dir)
    data.target_release = rev_parse_commit(data.target_release, data.project_dir)
    data.new_patch_parent = rev_parse_commit(data.new_patch_parent, data.project_dir)

    return data


def main():
    parser = argparse.ArgumentParser(
        description="Backports patch with the help of LLM",
        usage="%(prog)s --config CONFIG.yml\ne.g.: python %(prog)s --config CVE-examaple.yml",
    )
    parser.add_argument(
        "-c", "--config", type=str, required=True, help="CVE config yml"
    )
    parser.add_argument("-d", "--debug", action="store_true", help="enable debug mode")
    args = parser.parse_args()
    debug_mode = args.debug
    config_file = args.config
    if debug_mode:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    data = load_yml(config_file)

    need_patch_path = os.path.join(data.patch_dataset_dir, "need_backport.patch")
    try:
        if not os.path.isfile(need_patch_path):
            logger.info(f"need_backport.patch not found; creating {need_patch_path} from commit {data.new_patch}")
            show_out = subprocess.check_output(
                ["git", "-C", data.project_dir, "show", data.new_patch],
                stderr=subprocess.STDOUT,
                text=True,
            )
            with open(need_patch_path, "w") as f:
                f.write(show_out)
            logger.info(f"Created need_backport.patch: {need_patch_path}")
    except Exception as e:
        logger.error(f"Failed to create need_backport.patch: {e}")
    log_dir = "../logs"
    os.makedirs(log_dir, exist_ok=True)
    now = datetime.datetime.now().strftime("%m%d%H%M")
    logfile = os.path.join(log_dir, f"{data.project}-{data.tag}-{now}.log")
    add_file_handler(logger, logfile)

    subprocess.run(
        ["sudo", "chown", "-R", "lcj:lcj", "/home/lcj/linux-stable"],
        cwd=os.path.dirname(__file__),
        check=False,
    )

    runtime_config = os.path.join(data.patch_dataset_dir, "repro", "kernel.config.runtime")
    if os.path.isfile(runtime_config):
        os.remove(runtime_config)

    project = Project(data)
    project.repo.git.clean("-fdx")
    start_time = time.time()
    before_usage = safe_get_usage(data.api_key, data.api_url)
    agent_executor, llm = initial_agent(project, data, debug_mode)
    try:
        do_backport(agent_executor, project, data, llm, logfile)
        end_time = time.time()
        time.sleep(10)
        after_usage = safe_get_usage(data.api_key, data.api_url)
        if isinstance(after_usage, dict) and isinstance(before_usage, dict):
            logger.debug(
                f"This patch total cost: ${(after_usage['total_cost'] - before_usage['total_cost']):.2f}"
            )
            logger.debug(
                f"This patch total consume tokens: {(after_usage['total_consume_tokens'] - before_usage['total_consume_tokens'])/1000}(k)"
            )
        else:
            logger.debug("Failed to retrieve usage information.")
        logger.debug(
            f"This patch total cost time: {int(end_time - start_time)} Seconds."
        )
    except KeyboardInterrupt:
        logger.debug("Start to calculate cost!")
        end_time = time.time()

        after_usage = safe_get_usage(data.api_key, data.api_url)
        if isinstance(after_usage, dict) and isinstance(before_usage, dict):
            logger.debug(
                f"This patch total cost: ${(after_usage['total_cost'] - before_usage['total_cost']):.2f}"
            )
            logger.debug(
                f"This patch total consume tokens: {(after_usage['total_consume_tokens'] - before_usage['total_consume_tokens'])/1000}(k)"
            )
        else:
            logger.debug("Failed to retrieve usage information.")
        logger.debug(
            f"This patch total cost time: {int(end_time - start_time)} Seconds."
        )

    shutil.copy(logfile, data.patch_dataset_dir)


if __name__ == "__main__":
    main()
