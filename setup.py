#!/usr/bin/python
# -*- coding: utf-8 -*-


import distutils.command.sdist
import os
from distutils.command.install import INSTALL_SCHEMES
from distutils.core import setup

from scripts.include import get_files, get_git_date_and_time, get_git_version

# Add "git" to the end of the list to build from git commit
package_version = [0, 8, 0]
packages = ["covscan", "covscand", "covscanhub", "covscancommon"]
data_files = {
    "/etc/covscan": [
        "covscan/covscan.conf",
        "covscand/covscand.conf",
        "covscand/covscand.conf.prod",
        "covscand/covscand.conf.stage",
    ],
    "/etc/httpd/conf.d": [
        "covscanhub/covscanhub-httpd.conf.prod",
        "covscanhub/covscanhub-httpd.conf.stage",
    ],
    "/usr/lib/systemd/system": [
        "files/etc/systemd/system/covscand.service",
    ],
    "/etc/bash_completion.d": [
        "files/etc/bash_completion.d/covscan.bash",
    ],
    "/usr/bin": [
        "covscan/covscan",
    ],
    "/usr/sbin": [
        "covscand/covscand",
    ],
}
package_data = {
    "covscanhub": [
        "covscanhub.wsgi",
        "settings_local.py.prod",
        "settings_local.py.stage",
        "scripts/checker_groups.txt",
    ]
}

for folder in (
    "static",
    "templates",
    "media",
    "scan/fixtures",
    "errata/fixtures",
    "fixtures",
):
    package_data["covscanhub"].extend(get_files("covscanhub", folder))

# override default tarball format with bzip2
distutils.command.sdist.sdist.default_format = {
    "posix": "bztar",
}

if os.path.isdir(".git"):
    # we're building from a git repo -> store version tuple to __init__.py
    if package_version[-1] == "git":
        git_version = get_git_version(os.path.dirname(os.path.abspath(__file__)))
        git_date, git_time = get_git_date_and_time(
            os.path.dirname(os.path.abspath(__file__))
        )
        package_version += [git_date, git_time, git_version]


# force to install data files to site-packages
for scheme in INSTALL_SCHEMES.values():
    scheme["data"] = scheme["purelib"]


setup(
    name="covscan",
    version=".".join(map(str, package_version)),
    url="https://gitlab.cee.redhat.com/covscan/covscan",
    author="Red Hat, Inc.",
    author_email="ttomecek@redhat.com",
    description="Coverity scan scheduler",
    packages=packages,
    package_data=package_data,
    data_files=data_files.items(),
)
