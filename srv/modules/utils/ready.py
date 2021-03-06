# -*- coding: utf-8 -*-
# pylint: disable=modernize-parse-error
"""
Although similar to validate.py, the intention here is to run checks on
all minions in a cluster.  Additionally, these checks are not absolute so
a warning is more appropriate.

"""

from __future__ import absolute_import
from __future__ import print_function
import logging
from collections import OrderedDict
# pylint: disable=import-error,3rd-party-module-not-gated,redefined-builtin
import salt.client
import salt.utils.error


log = logging.getLogger(__name__)


# pylint: disable=no-init,too-few-public-methods
class Bcolors(object):
    """
    Define escape sequences
    """
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Checks(object):
    """
    Define a collection of checks to run Salt minions
    """

    def __init__(self, search):
        """
        Set search criteria
        """
        self.search = search
        self.passed = OrderedDict()
        self.warnings = OrderedDict()
        self.local = salt.client.LocalClient()

    def firewall(self):
        """
        Scan all minions for the default firewall settings.  Set warnings
        for any differences.
        """
        contents = self.local.cmd(self.search, 'cmd.run_all',
                                  ['/usr/sbin/iptables -S'],
                                  tgt_type="compound")

        for minion in contents:
            if contents[minion]['retcode'] == 127:
                self.passed['firewall'] = "not installed"
                continue
            if 'firewall' in self.passed:
                del self.passed['firewall']

            # Accept custom named chains
            if not contents[minion]['stdout'].startswith(("-P INPUT ACCEPT\n"
                                                          "-P FORWARD ACCEPT\n"
                                                          "-P OUTPUT ACCEPT")):
                msg = "enabled on minion {}".format(minion)
                if 'firewall' in self.warnings:
                    self.warnings['firewall'].append(msg)
                else:
                    self.warnings['firewall'] = [msg]
        if 'firewall' not in self.warnings and 'firewall' not in self.passed:
            self.passed['firewall'] = "disabled"

    def apparmor(self):
        """
        Scan minions for apparmor settings.
        """
        contents = self.local.cmd(self.search, 'cmd.shell',
                                  [('/usr/sbin/aa-status --enabled '
                                    '2>/dev/null; echo $?')],
                                  tgt_type="compound")
        # check if all file.managed for the profiles would apply
        # cleanly using test=True. If so salt returns 'result': True
        # burried in its return structure
        profile_test = self.local.cmd(self.search, 'state.apply',
                                      ['ceph.apparmor.profiles'],
                                      kwarg={'test': 'true'},
                                      tgt_type="compound")

        minions_with_apparmor = 0
        minions_with_profiles = 0
        for minion in contents:
            if contents[minion] and int(contents[minion]) == 0:
                minions_with_apparmor += 1
                # aggregate the number of 'result': True we got
                profiles_present = [v['result'] for k, v in
                                    profile_test[minion].items()
                                    if v['result']]
                # and compare to number of file.managed state we have, i.e. the
                # number of profiles
                if len(profile_test[minion]) == len(profiles_present):
                    minions_with_profiles += 1
        if minions_with_apparmor == 0:
            self.passed['apparmor'] = "disabled"
        else:
            msg = ('enabled on {}/{} minions; {} minions have all ceph.apparmor'
                   ' profiles').format(minions_with_apparmor,
                                       len(profile_test),
                                       minions_with_profiles)
            if minions_with_apparmor == minions_with_profiles:
                self.passed['apparmor'] = msg
            else:
                self.warnings['apparmor'] = msg

    def report(self):
        """
        Produce nicely colored output
        """
        for attr in self.passed.keys():
            print("{:25}: {}{}{}{}".format(attr, Bcolors.BOLD, Bcolors.OKGREEN,
                                           self.passed[attr], Bcolors.ENDC))
        for attr in self.warnings.keys():
            print("{:25}: {}{}{}{}".format(attr, Bcolors.BOLD, Bcolors.WARNING,
                                           self.warnings[attr], Bcolors.ENDC))


def help_():
    """
    Usage
    """
    usage = ('salt-run ready.check:\n'
             'salt-run ready.check search=target:\n'
             'salt-run ready.check fail_on_warning=False:\n\n'
             '    Check for firewall and apparmor configurations\n'
             '\n\n')
    print(usage)
    return ""


def check(cluster, fail_on_warning=True, **kwargs):
    """
    Check a cluster for runtime configurations that may cause issues for an
    installation.
    """
    if cluster is None:
        cluster = kwargs['cluster']

    search = "I@cluster:{}".format(cluster)

    _check = Checks(search)
    _check.firewall()
    _check.apparmor()
    _check.report()

    if _check.warnings and fail_on_warning:
        __context__['retcode'] = 1
        return False
    return True

__func_alias__ = {
                 'help_': 'help',
                 }
