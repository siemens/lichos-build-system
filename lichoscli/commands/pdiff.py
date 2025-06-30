import logging

from lichoscli.utils import BuildUtils, GitUtils
from lichoscli.commands.base import Command
from lichoscli.pkg import PkgGroupHandler

logger = logging.getLogger(__name__)


class PDiffCommand(Command):
    """print diff to parent"""

    def __init__(self, pkg_group_handler: PkgGroupHandler, args):
        super().__init__(pkg_group_handler=pkg_group_handler, args=args)
        self.package_name = BuildUtils.get_package_name(args.package)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")

    def execute(self):
        repo = GitUtils.get_git_repo()

        if not repo:
            logger.error("No git repository found")
            return 1

        if "parent" not in repo.remotes:
            logger.error("Missing parent repo")
            return False

        parent = repo.remotes.parent
        refname = repo.head.reference

        if str(refname) not in parent.refs:
            pbr = [str(r).split("/", 2)[1] for r in repo.remotes.parent.refs]
            logger.warning(
                "parent repo does not have %s branch, trying %s", refname, pbr[0]
            )
            pref = repo.remotes.parent.refs[pbr[0]]
        else:
            pref = repo.remotes.parent.refs[str(refname)]

        oref = repo.remotes.origin.refs[str(refname)]

        for d in pref.commit.diff(oref.commit, create_patch=True):
            a = f"a/{d.a_blob.path}" if d.a_blob and d.a_blob.path else "/dev/null"
            b = f"b/{d.b_blob.path}" if d.b_blob and d.b_blob.path else "/dev/null"
            print(f"diff {oref} {pref}")
            print(f"--- {a}\n+++ {b}")
            print(d.diff.decode("utf-8"))

        return 0
