import os
import json
import platform
import configparser
import traceback

import click
import docker

DOCKERFILE = """
FROM {base_image}

WORKDIR /var/task

# Fancy prompt to remind you are in ZappaDock
RUN echo 'export PS1="\[\e[36m\]ZappaDock>\[\e[m\] "' >> /root/.bashrc && \\
    yum clean all && \\
    yum install -y which clang cmake python-devel python3-devel amazon-linux-extras gcc openssl-devel bzip2-devel libffi-devel wget tar gzip make postgresql-devel && \\
    echo 'virtualenv -p python3 ./zappa-layer-venv >/dev/null' >> /root/.bashrc && \\
    echo 'virtualenv -p python3 ./zappa-code-venv >/dev/null' >> /root/.bashrc && \\
    echo 'source ./zappa-code-venv/bin/activate >/dev/null' >> /root/.bashrc

CMD ["bash"]
"""

def colored_echo(text, color=None):
    bold = False
    if not text.startswith("  ") and not text.startswith(" "):
        color = "cyan"
        bold = True
    return click.echo(click.style(text, fg=color, bold=bold))

@click.command()
@click.option(
    "--image_source",
    type=click.Choice(["build", "pull", "pull_default"]),
    required=False,
    default="pull_default",
    help="Specify how to get image.",
)
@click.option(
    "--platform",
    type=click.Choice(["linux/amd64", "linux/arm64", "linux/arm/v7"]),
    required=False,
    help="Specify platform to build or pull image for. (if image support multi-arch)"
)
def zappadock(image_source, platform):
    """This is a tool for running Zappa commands in a Lambda-like environment.

    Make sure the Docker daemon is installed and running before using this tool.

    Your AWS credentials must be setup to use this tool.
    See https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html#environment-variables for more information.
    """
    # Set Zappadock Docker Filename
    docker_file = ".zappadock-Dockerfile"
    project_name = os.path.basename(os.getcwd())

    # If container is already running, attach to it
    docker_client = docker.from_env()
    is_existing_container = False
    for container in docker_client.containers.list():
        if container.name == f"zappadock-layer-{project_name}":
            colored_echo("Attaching to existing container.")
            os.system(f"docker attach {container.name}")
            exit(0)
    
    # Get image source if not specified
    if image_source == "build":
        image_source_choice = "1"
    elif image_source in ["pull", "pull_default"]:
        image_source_choice = "2"
    else:
        colored_echo("Choose how to get zappadock-layer image")
        colored_echo("1. Pull from Docker Hub")
        colored_echo("2. Build from built-in Dockerfile")
        image_source_choice = click.prompt(
            "option:",
            type=click.Choice(["1", "2"]),
            show_choices=False,
            default="1",
            show_default=True,
            prompt_suffix=" ",
        )
    
    # Get repository name if image_source is "pull"
    if image_source_choice == "2":
        if image_source == "pull_default":
            repository_name = "esc5221/zappadock-layer:python3.9-x86_64"
        else:
            repository_name = click.prompt(
                "Enter repository name and tag",
                default="esc5221/zappadock-layer:python3.9-x86_64",
                show_default=True,
                prompt_suffix=" ",
            )
    else:
        repository_name = None

    # Summarize docker image source
    colored_echo("Summary of docker image")
    colored_echo(f"  Image Source: {image_source}")
    colored_echo(f"  Repository  : {repository_name}")
    colored_echo(f"  Platform    : {platform}")
    colored_echo("")

    docker_run_command = ["docker run -ti --rm"]
    docker_run_command.append(f"--name zappadock-layer-{project_name}")  # @dev add container name
    # @dev add platform as linux/amd64
    docker_run_command.append("--platform linux/amd64")

    # Add mount command to .aws folder if it exists
    if os.path.isdir(os.path.expanduser("~/.aws")):
        docker_run_command.append(f"-v ~/.aws/:/root/.aws")

    # Add AWS Environment Variables to Docker Command if they exist
    for i in [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
        "AWS_PROFILE",
    ]:
        if i in os.environ:
            docker_run_command.append(f"-e {i}={os.environ[i]}")

    # Get zapppadock-layer image

    # 1. Build image from Dockerfile
    if image_source_choice == "1":
        # Create Dockerfile if it doesn't exist
        if not os.path.isfile(docker_file):
            colored_echo(f"Creating Dockerfile.")
            with open(docker_file, "w") as f:

                # Find the current running Python version
                python_version = ".".join(platform.python_version().split(".")[:2])

                # Check if the current Python version is supported
                if python_version not in ["3.6", "3.7", "3.8", "3.9"]:
                    colored_echo(
                        f"Python version {python_version} is not supported. Please use 3.6, 3.7, 3.8, or 3.9."
                    )
                    exit()

                # Check the current architecture
                if platform.machine().lower() in [
                    "aarch64",
                    "arm64",
                    "armv7l",
                    "armv8l",
                ] and python_version in ["3.6", "3.7"]:
                    colored_echo(
                        "AWS Lambda does not support Python 3.6 or 3.7 on ARM64 on devices."
                    )
                    exit()

                # Get the base image
                if python_version in ["3.8", "3.9"]:
                    image = f"mlupin/docker-lambda:python{python_version}-build"
                else:
                    image = f"lambci/lambda:build-python{python_version}"

                # Write the Dockerfile
                f.write(DOCKERFILE.format(base_image=image))

        try:
            # Create Docker client
            colored_echo("Creating Docker client.")
            client = docker.from_env()

        except docker.errors.DockerException as e:

            if "Permission denied" in str(e):
                # If the user doesn't have permission to run docker, let them know
                colored_echo(
                    "Your user is not in the docker group.\nSee https://docs.docker.com/engine/install/linux-postinstall/#manage-docker-as-a-non-root-user for more information."
                )
            else:
                # Docker isn't installed / running
                colored_echo(
                    f"{traceback.format_exc()}\n\nDocker failed to load.\nMake sure its installed and running before continuing."
                )
            colored_echo("Exiting...")
            exit()

        # Build Docker Image
        with open(docker_file, "rb") as f:
            try:
                colored_echo("Building Docker Image. This may take some time...")
                docker_image = client.images.build(
                    fileobj=f,
                    tag="zappadock-layer",
                    platform=platform,
                    quiet=False,
                )
            except docker.errors.DockerException as e:
                colored_echo(
                    f"{traceback.format_exc()}\n\nDocker failed to build.\nCheck the Dockerfile for any mistakes."
                )
                colored_echo("Exiting...")
                exit()

    # 2. Pull image from Docker Hub
    elif image_source_choice == "2":
        # If Image already exists, use it
        for image in docker_client.images.list():
            for tag in image.tags:
                if tag == repository_name:
                    colored_echo("Using existing image...")
                    docker_image = image
                    break
        # Pull Docker Image
        if docker_image is None:
            colored_echo("Pulling from Docker Hub...")
            docker_image = docker_client.images.pull(
                repository_name, platform=platform
            )

    if type(docker_image) == list:
        docker_image = docker_image[0]

    # Create command to start ZappaDock
    docker_run_command.append(
        f'-v "{os.getcwd()}:/var/task" -p 8000:8000 {docker_image.id}'
    )
    colored_echo("Docker Command :")
    for i in docker_run_command:
        if i.startswith("docker"): 
            colored_echo(f"  {i}")
        else:
            colored_echo(f"    {i}")
    colored_echo("")

    # Start ZappaDock
    colored_echo("Starting ZappaDock...")
    os.system(" ".join(docker_run_command))


if __name__ == "__main__":
    zappadock()
