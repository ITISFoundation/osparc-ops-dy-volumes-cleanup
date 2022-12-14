import asyncio
import logging
from enum import Enum
from pathlib import Path

import typer

logger = logging.getLogger(__name__)

R_CLONE_CONFIG = """
[dst]
type = s3
provider = {destination_provider}
access_key_id = {destination_access_key}
secret_access_key = {destination_secret_key}
endpoint = {destination_endpoint}
region = {destination_region}
acl = private
"""


class S3Provider(str, Enum):
    AWS = "AWS"
    CEPH = "CEPH"
    MINIO = "Minio"


def get_config_file_path(
    s3_endpoint: str,
    s3_access_key: str,
    s3_secret_key: str,
    s3_region: str,
    s3_provider: S3Provider,
) -> Path:
    config_content = R_CLONE_CONFIG.format(
        destination_provider=s3_provider,
        destination_access_key=s3_access_key,
        destination_secret_key=s3_secret_key,
        destination_endpoint=s3_endpoint,
        destination_region=s3_region,
    )
    conf_path = Path("/tmp/rclone_config.ini")  # nosec
    conf_path.write_text(config_content)  # pylint:disable=unspecified-encoding
    return conf_path


def _get_s3_path(s3_bucket: str, labels: dict[str, str]) -> Path:
    joint_key = "/".join(
        (
            s3_bucket,
            labels["swarm_stack_name"],
            labels["study_id"],
            labels["node_uuid"],
            labels["run_id"],
        )
    )
    return Path(f"/{joint_key}")


async def store_to_s3(  # pylint:disable=too-many-locals
    dyv_volume: dict,
    s3_endpoint: str,
    s3_access_key: str,
    s3_secret_key: str,
    s3_bucket: str,
    s3_region: str,
    s3_provider: S3Provider,
    s3_retries: int,
    s3_parallelism: int,
    exclude_files: list[str],
) -> None:
    config_file_path = get_config_file_path(
        s3_endpoint=s3_endpoint,
        s3_access_key=s3_access_key,
        s3_secret_key=s3_secret_key,
        s3_region=s3_region,
        s3_provider=s3_provider,
    )

    source_dir = dyv_volume["Mountpoint"]
    s3_path = _get_s3_path(s3_bucket, dyv_volume["Labels"])

    r_clone_command = [
        "rclone",
        "--config",
        f"{config_file_path}",
        "--low-level-retries",
        "3",
        "--retries",
        f"{s3_retries}",
        "--transfers",
        f"{s3_parallelism}",
        "sync",
        f"{source_dir}",
        f"dst:{s3_path}",
        "-P",
    ]
    # ignore files
    for to_exclude in exclude_files:
        r_clone_command.append("--exclude")
        r_clone_command.append(to_exclude)

    str_r_clone_command = " ".join(r_clone_command)
    typer.echo(r_clone_command)

    process = await asyncio.create_subprocess_shell(
        str_r_clone_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()

    if process.returncode != 0:
        raise RuntimeError(
            f"Shell subprocesses yielded nonzero error code {process.returncode} "
            f" for command {str_r_clone_command}\n{stdout.decode()}"
        )
