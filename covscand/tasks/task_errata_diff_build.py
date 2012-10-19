# -*- coding: utf-8 -*-

import tempfile
import os
from kobo.shortcuts import run
import pipes
import sys
import grp
import shutil
from kobo.rpmlib import get_rpm_header
from kobo.worker import TaskBase
import logging
import kobo.tback


class ErrataDiffBuild(TaskBase):
    """
        Execute diff scan between two versions/releases of a package for
        Errata Tool
    """
    enabled = True

    # list of supported architectures
    arches = ["noarch"]
    # list of channels
    channels = ["default"]
    # leave False here unless you really know what you're doing
    exclusive = False
    # if True the task is not forked and runs in the worker process
    # (no matter you run worker without -f)
    foreground = False
    priority = 20
    weight = 1.0

    def run(self):
        DEBUG = True
        logging.basicConfig(
            format='%(asctime)s %(levelname)8s %(message)s',
            filename='/tmp/covscand_task.log',
            level=logging.DEBUG
        )

        logging.debug("I'm about to set scan %s to state 'SCANNING'" %
                      self.args['scan_id'])
        self.hub.worker.set_scan_to_scanning(self.args['scan_id'])

        mock_config = self.args.pop("mock_config")
        #keep_covdata = self.args.pop("keep_covdata", False)
        #all_checks = self.args.pop("all", False)
        #security_checks = self.args.pop("security", False)
        brew_build = self.args.pop("brew_build", None)

        # create a temp dir
        tmp_dir = tempfile.mkdtemp(prefix="covscan_")
        os.chmod(tmp_dir, 0775)
        srpm_path = os.path.join(tmp_dir, "%s.src.rpm" % brew_build)

        if not DEBUG:
            # make the dir writable by 'coverity' user
            coverity_gid = grp.getgrnam("coverity").gr_gid
            os.chown(tmp_dir, -1, coverity_gid)

            #download srpm from brew
            logging.debug('I am about to download %s', brew_build)
            cmd = ["brew", "download-build", "--quiet",
                   "--arch=src", brew_build]
            run(cmd, workdir=tmp_dir)

            if not os.path.exists(srpm_path):
                print >> sys.stderr, \
                    "Invalid path %s to SRPM file (%s): %s" % \
                    (srpm_path, brew_build, kobo.tback.get_exception())
                self.fail()

            #is srpm allright?
            try:
                get_rpm_header(srpm_path)
            except Exception:
                print >> sys.stderr, "Invalid RPM file(%s): %s" % \
                    (brew_build, kobo.tback.get_exception())
                self.fail()

        #execute mockbuild of this package
        cov_cmd = []
        cov_cmd.append("cd")
        cov_cmd.append(pipes.quote(tmp_dir))
        cov_cmd.append(";")

        # $program [-fit] MOCK_PROFILE my-package.src.rpm [COV_OPTS]
        cov_cmd.append('cov-mockbuild')
        #if keep_covdata:
        #    cov_cmd.append("-i")
        cov_cmd.append(pipes.quote(mock_config))
        cov_cmd.append(pipes.quote(srpm_path))
        #if all_checks:
        #    cov_cmd.append("--all")
        #if security_checks:
        #    cov_cmd.append("--security")

        command = ["su", "-", "coverity", "-c", " ".join(cov_cmd)]

        if not DEBUG:
            retcode, output = run(command, can_fail=False, stdout=True)
        else:
            command_str = ' '.join(command)
            logging.info("In production I would run this command: %s",
                         command_str)
            retcode = 0

        # upload results back to hub

        if DEBUG:
            logging.debug('I am about to copy test tarball')
            shutil.copy2('/tmp/' + brew_build + '.tar.xz', tmp_dir)

        logging.debug('I am about to upload tarball')
        xz_path = srpm_path[:-8] + ".tar.xz"
        if not os.path.exists(xz_path):
            xz_path = srpm_path[:-8] + ".tar.lzma"
        self.hub.upload_task_log(open(xz_path, "r"),
                                 self.task_id, os.path.basename(xz_path))

        logging.debug('I am about to extract tarball')
        try:
            self.hub.worker.extract_tarball(self.task_id, '')
        except Exception, ex:
            logging.error("got exception %s, trace:\n%s", str(ex),
                          kobo.tback.get_exception())
            self.fail()

        # remove temp files
        shutil.rmtree(tmp_dir)

        if retcode:
            self.fail()

        self.hub.worker.finish_scan(self.args['scan_id'])

    @classmethod
    def cleanup(cls, hub, conf, task_info):
        pass
        # remove temp files, etc.

    @classmethod
    def notification(cls, hub, conf, task_info):
        pass
        #hub.worker.email_task_notification(task_info["id"])
