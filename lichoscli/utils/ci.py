import logging
import re
from collections import namedtuple

from .constants import CI_DEFAULT_PIPELINE_NAME, CI_PKG, CI_TEMPLATE

logger = logging.getLogger(__name__)


class CIConfigUtils:
    """Handle CI/CD configuration and pipeline operations"""

    @staticmethod
    def parse_ci_config_path(path):
        P = namedtuple("P", ["name", "group", "pkg", "branch"])
        r = re.match(
            r"(?P<name>[^@]+).yml(?:@(?P<group>[^:]*)/(?P<pkg>[^/:]+)(?::(?P<branch>.*))?)?$",
            path,
        )
        if r is None:
            return None

        return P(r.group("name"), r.group("group"), r.group("pkg"), r.group("branch"))

    @staticmethod
    def get_ci_path(group_rpath, ci_typ=CI_DEFAULT_PIPELINE_NAME, branch=None):
        ci = CI_TEMPLATE.format(name=ci_typ, group=group_rpath, pkg=CI_PKG)
        if branch:
            ci += ":" + branch
        return ci
