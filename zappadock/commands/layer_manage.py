import os
import subprocess
import json
from datetime import datetime
import click

import typing as t
import click
from click.decorators import command
from click.core import Command, Context, Group, Option, Parameter, ParameterSource, HelpFormatter
from gettext import gettext as _

F = t.TypeVar("F", bound=t.Callable[..., t.Any])

def colored_echo(text, color=None):
    bold = False
    if not text.startswith("  ") and not text.startswith(" "):
        color = "cyan"
        bold = True
    return click.echo(click.style(text, fg=color, bold=bold))

class ColoredGroup(Group):
    subcommand_sections = [
        {
            "name": "package",
            "ends_with": "pkgs"
        },
        {
            "name": "layer",
            "ends_with": "layer"
        },
    ]

    def format_options(self, ctx: Context, formatter: HelpFormatter) -> None:
        """Writes all the options into the formatter if they exist."""
        opts = []
        for param in self.get_params(ctx):
            rv = param.get_help_record(ctx)
            if rv is not None:
                opts.append(rv)

        if opts:
            with formatter.section(_(click.style("Options", bold=True))):
                formatter.write_dl(opts)

        self.format_commands(ctx, formatter)

    def format_commands(self, ctx: Context, formatter: HelpFormatter) -> None:
        """Extra format methods for multi methods that adds all the commands
        after the options.
        """
        commands = []
        reversed_commands = reversed(self.list_commands(ctx))
        for subcommand in reversed_commands:
            cmd = self.get_command(ctx, subcommand)
            # What is this, the tool lied about a command.  Ignore it
            if cmd is None:
                continue
            if cmd.hidden:
                continue

            commands.append((subcommand, cmd))

        # allow for 3 times the default spacing
        if len(commands):
            limit = formatter.width - 6 - max(len(cmd[0]) for cmd in commands)

            rows = []
            for subcommand_section in self.subcommand_sections:
                name = subcommand_section["name"]
                rows.append(("", ""))
                rows.append((click.style(f"[{name}]", bold=True, fg="red"), ""))
            for subcommand, cmd in commands:
                help = cmd.get_short_help_str(limit)
                for subcommand_section in self.subcommand_sections:
                    if subcommand.endswith(subcommand_section["ends_with"]):
                        # insert next to the section
                        rows.insert(
                            rows.index((click.style(f"[{subcommand_section['name']}]", bold=True, fg="red"), "")) + 1,
                            (click.style("   "+subcommand,bold=True), click.style(help,fg="bright_black"))
                        )
                        break

            if rows:
                with formatter.section(_(click.style("Available subcommands", bold=True))):
                    formatter.write_dl(rows)

def colored_group(name: t.Optional[str] = None, **attrs: t.Any) -> t.Callable[[F], ColoredGroup]:
    """Creates a new :class:`Group` with a function as callback.  This
    works otherwise the same as :func:`command` just that the `cls`
    parameter is set to :class:`Group`.
    """
    attrs.setdefault("cls", ColoredGroup)
    return t.cast(ColoredGroup, command(name, **attrs))


@colored_group(
    help="Manage layers for zappadock",
)
def cli():
    pass

@cli.command(
    help="Check packages in venv",
)
@click.argument("venv_type", type=click.Choice(["code", "layer"]))
def checkpkgs(venv_type):
    venv_name = f"zappa-{venv_type}-venv"
    # get site package path for venv
    site_packages_path = os.path.join(os.getcwd(), venv_name, "lib", "python3.9", "site-packages")
    colored_echo(f"Checking site packages in {site_packages_path}")
    # colored_echo pip freeze from site_packages_path
    subprocess.call(f"pip freeze --path {site_packages_path}", shell=True)
    
@cli.command(
    help="Install packages in venv (default: in layer)",
)
@click.argument("venv_type", type=click.Choice(["code", "layer"]), default="layer")
def installpkgs(venv_type):
    venv_name = f"zappa-{venv_type}-venv"
    # get site package path for venv
    site_packages_path = os.path.join(os.getcwd(), venv_name, "lib", "python3.9", "site-packages")
    colored_echo(f"Installing packages to {site_packages_path}")
    # install requirements.txt to site_packages_path
    subprocess.call(f"pip install -r requirements.txt -t {site_packages_path}", shell=True)

@cli.command(
    help="Make layer.zip from zappa-layer-venv",
)
@click.argument("mode", type=click.Choice(["new", "update"]), default="update")
def makelayer(mode):
    venv_type = "layer"
    venv_name = f"zappa-{venv_type}-venv"
    # get site package path for venv
    site_packages_path = os.path.join(os.getcwd(), venv_name, "lib", "python3.9", "site-packages")

    # # copy packages into python
    parent_of_site_package_path = os.path.dirname(site_packages_path)
    colored_echo("Site packages path:")
    colored_echo("  "+site_packages_path)
    # change site_packages_path name to python
    colored_echo('Change site_packages_path name as python...')
    try:
        subprocess.call(f'cd /{parent_of_site_package_path} && mv site-packages python', shell=True)
        colored_echo('  Done.')
    except:
        pass
    else:
        time_stamp = datetime.now().strftime('%Y%m%d%H%M%S')
        colored_echo(f'Creating layer zip with {mode} mode...')
        if mode == 'new':
            # delete old zip
            subprocess.call(f'cd /{parent_of_site_package_path} && rm layer.zip', shell=True)
            subprocess.call(f'cd /{parent_of_site_package_path} && zip --quiet -r -v -X layer.zip python -x "**/__pycache__/*"', shell=True, stdout=subprocess.DEVNULL)
        elif mode == 'update':
            subprocess.call(f'cd /{parent_of_site_package_path} && zip -u --quiet -r -v -X layer.zip python -x "**/__pycache__/*"', shell=True, stdout=subprocess.DEVNULL)
        colored_echo('  Done.')

    finally:
        colored_echo('Restore site_packages_path name...')
        subprocess.call(f'cd /{parent_of_site_package_path} && mv python site-packages', shell=True)
        colored_echo('  Done.')

    # move layer to current directory
    colored_echo('Copy layer to current directory...')
    subprocess.call(f'cd /{parent_of_site_package_path} && cp layer.zip /{os.getcwd()}/layer.zip', shell=True)
    colored_echo('  Done.')

    colored_echo('Layer zip file created at:')
    colored_echo(f'  {os.getcwd()}/layer.zip')


@cli.command(
    help="Publish layer to AWS",
)
@click.option("--profile", "-p", help="AWS profile name, defalult: [project_name]_dev")
@click.option("--layer_name", "-l", help="Layer name, default: [project_name]_layer")
@click.option("--region", "-r", default="ap-northeast-2", help="AWS region")
def publishlayer(profile, layer_name, region):
    project_name = os.path.basename(os.getcwd())
    if layer_name is None:
        layer_name = f"{project_name}_layer"
    if not profile:
        profile = project_name+"_dev"

    aws_credentials_path = os.path.join(os.path.expanduser("~"), ".aws", "credentials")
    with open(aws_credentials_path, "r") as f:
        if f"[{profile}]" not in f.read():
            colored_echo(f"Profile {profile} not found in {aws_credentials_path}, using default profile")
        else:
            colored_echo(f"Using aws profile:")
            colored_echo(f"  {profile}")

    colored_echo("PublishLayer command:")
    colored_echo(
        f"  aws lambda publish-layer-version\n" + 
        f"    --zip-file fileb://layer.zip\n" +
        f"    --layer-name {layer_name}\n" +
        f"    --profile {profile}\n" +
        f"    --region {region}\n"
    )
                
    colored_echo("Publishing layer...")
    layer_output = subprocess.check_output(
        [
            f"aws lambda publish-layer-version" + 
            f" --zip-file fileb://layer.zip" +
            f" --layer-name {layer_name}" +
            f" --profile {profile}" +
            f" --region {region}",
        ],
        shell=True,
    )
    click.echo(layer_output)
    colored_echo("  Done.")

@cli.command(
    help="Publish layer to AWS",
)
@click.option("--profile", "-p", help="AWS profile name, defalult: [project_name]_dev")
@click.option("--layer_name", "-l", help="Layer name, default: [project_name]_layer")
@click.option("--region", "-r", default="ap-northeast-2", help="AWS region")
def updatezappalayer(profile, layer_name, region):
    project_name = os.path.basename(os.getcwd())
    if layer_name is None:
        layer_name = f"{project_name}_layer"
    if not profile:
        profile = project_name+"_dev"

    aws_credentials_path = os.path.join(os.path.expanduser("~"), ".aws", "credentials")
    with open(aws_credentials_path, "r") as f:
        if f"[{profile}]" not in f.read():
            colored_echo(f"Profile {profile} not found in {aws_credentials_path}, using default profile")
        else:
            colored_echo(f"Using aws profile:")
            colored_echo(f"  {profile}")
                
    colored_echo("Latest layer version:")
    layer_output = subprocess.check_output(
        [
            f"aws lambda list-layer-versions" + 
            f" --query LayerVersions[0].Version " +
            f" --layer-name {layer_name}" +
            f" --profile {profile}" +
            f" --region {region}",
        ],
        shell=True,
    )
    colored_echo(f"  {int(layer_output)}")
    latest_layer_version = int(layer_output)

    with open('zappa_settings.json', 'r') as f:
        zappa_settings = json.load(f)
        layers = zappa_settings['dev']['layers']
        layer = layers[0]
        *layer_info, old_layer_version = layer.split(':')
        new_layer = ':'.join(layer_info) + ':' + str(latest_layer_version)
        colored_echo("New layer info:")
        colored_echo(f"  {new_layer}")
        layers[0] = new_layer
        zappa_settings['dev']['layers'] = layers

    # save zappa_settings.json
    with open('zappa_settings.json', 'w') as f:
        colored_echo('Save zappa_settings.json')
        json.dump(zappa_settings, f, indent=4)
        # print zappa_settings.json pretty
        click.echo(json.dumps(zappa_settings, indent=4))

if __name__ == "__main__":
    cli()