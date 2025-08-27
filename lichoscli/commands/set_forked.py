import logging
from gitlab import GitlabError
from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class SetForkedCommand(Command):
    """Set fork relationship to a parent project"""

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler=pkg_group_handler, args=args)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", help="some package name")
        sp.add_argument("parent", help="parent package")

    def execute(self):
        pn = BuildUtils.get_package_name(self.args.package)
        pkg = None
        if pn:
            pkg = self.pkg_group_handler.get_package(pn)

        if pn is None or pkg is None:
            logger.error("Can't find %s", pn)
            return 1

        try:
            pprj = self.pkg_group_handler.gitlab.projects.get(self.args.parent)
        except GitlabError as e:
            logger.error("%s: %s", self.args.parent, e)
            return 1

        try:
            pkg.create_fork_relation(pprj.id)
        except GitlabError as e:
            logger.error("%s: %s", pn, e)
            return 1

        return 0
