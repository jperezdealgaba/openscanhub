# -*- coding: utf-8 -*-

import brew
import koji
import os
import re

from xmlrpclib import Fault


__all__ = (
    "verify_brew_koji_build",
    "verify_mock",
    "handle_perm_denied",
)


# took this directly from koji source
# <koji_git_repo>/koji/__init__.py:153
KOJI_BUILD_STATES = (
    'BUILDING',
    'COMPLETE',
    'DELETED',
    'FAILED',
    'CANCELED',
)


def verify_build_exists(build, url, builder):
    """
    Verify if build exists
    """
    proxy_object = builder.ClientSession(url)
    try:
        # getBuild XML-RPC call is defined here: ./hub/kojihub.py:3206
        returned_build = proxy_object.getBuild(build)
    except brew.GenericError:
        return False
    except koji.GenericError:
        return False
    if returned_build is None:
        return False
    if 'state' in returned_build and \
            returned_build['state'] != KOJI_BUILD_STATES.index('COMPLETE'):
        return False
    return True


def verify_brew_koji_build(build, brew_url, koji_url):
    """
    Verify if brew or koji build exists
    """
    srpm = os.path.basename(build)  # strip path if any
    if srpm.endswith(".src.rpm"):
        srpm = srpm[:-8]

    try:
        dist_tag = re.search('.*-.*-(.*)', srpm).group(1)
    except AttributeError:
        return 'Invalid N-V-R: %s' % srpm

    error_template = "Build %s does not exist in koji nor in brew, or has its \
files deleted, or did not finish successfully." % build

    koji_build_exists = True
    if 'fc' in dist_tag:
        koji_build_exists = verify_build_exists(srpm, koji_url, koji)
        if koji_build_exists:
            return None
    brew_build_exists = verify_build_exists(srpm, brew_url, brew)
    if not brew_build_exists and not koji_build_exists:
        return error_template
    elif not brew_build_exists:
        koji_build_exists = verify_build_exists(srpm, koji_url, koji)
        if not brew_build_exists and not koji_build_exists:
            return error_template
        else:
            return None
    else:
        return None


def verify_mock(mock, hub):
    mock_conf = hub.mock_config.get(mock)
    if not mock_conf:
        return "Mock config %s does not exist." % mock
    if not mock_conf["enabled"]:
        return "Mock config %s is not enabled." % mock
    return None


def handle_perm_denied(e, parser):
    """DRY"""
    if 'PermissionDenied: Login required.' in e.faultString:
        parser.error('You are not authenticated. Please \
obtain Kerberos ticket or specify username and password.')
    else:
        raise


def upload_file(hub, srpm, target_dir, parser):
    """Upload file to hub, catch PermDenied exception"""
    try:
        #returns (upload_id, err_code, err_msg)
        return hub.upload_file(os.path.expanduser(srpm), target_dir)
    except Fault, e:
        handle_perm_denied(e, parser)
