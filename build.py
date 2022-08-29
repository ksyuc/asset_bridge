import requests
import subprocess
import argparse
from zipfile import ZipFile
from pathlib import Path
import webbrowser
import re


def update_init_file(init_file: Path, version: tuple):
    """Update the addon version in the init file"""
    with open(init_file, "r") as file:
        text = file.read()

    version = tuple(version)
    str_version = [str(v) for v in version]
    matcher = '"name".*:.*,'
    name_match = re.findall(matcher, text)
    matcher = '"version".*:.*,'
    version_match = re.findall(matcher, text)
    text = text.replace(name_match[0], f'"name": "Asset Bridge {".".join(str_version)}",')
    text = text.replace(version_match[0], f'"version": {str(version)},')

    with open(init_file, "w") as file:
        file.write(text)


def update_constants_file(constants_file, value):
    with open(constants_file, "r") as file:
        text = file.read()

    matcher = '__IS_DEV__.*=.*'
    name_match = re.findall(matcher, text)
    text = text.replace(name_match[0], f'__IS_DEV__ = {str(value)}')

    with open(constants_file, "w") as file:
        file.write(text)


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v",
        "--version",
        help="The version number to use, in the format '0.0.1'",
        default="",
        type=str,
    )
    args = parser.parse_args()

    path = Path(__file__).parent
    files = [Path(f.decode("utf8")) for f in subprocess.check_output("git ls-files", shell=True).splitlines()]
    files = [f for f in files if "asset_bridge\\" in str(f)]

    # version
    if args.version:
        file_version = args.version.replace(".", "_")
    else:
        res = requests.get("https://api.github.com/repos/strike-digital/asset_bridge/releases").json()[0]
        latest_version: str = res["tag_name"]
        subversion = latest_version.split(".")[-1]

        file_version = "_".join(latest_version.split(".")[:-1] + [str(int(subversion) + 1)])

    print(f"Zipping version '{file_version}'")
    update_init_file(path / "asset_bridge" / "__init__.py", tuple(int(f) for f in file_version.split("_")))
    constants_file = path / "asset_bridge" / "constants.py"
    update_constants_file(constants_file, False)

    out_path = path / "builds" / f"asset_bridge_{file_version}.zip"
    out_path.mkdir(exist_ok=True)

    with ZipFile(out_path, 'w') as z:
        for file in files:
            z.write(file, arcname=str(file).replace("asset_bridge", f"asset_bridge_{file_version}"))
    update_constants_file(constants_file, True)

    webbrowser.open(out_path.parent)


if __name__ == "__main__":
    main()