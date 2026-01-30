import logging
from pathlib import Path

from lichoscli.commands.base import Command
from lichoscli.core.di import DIContainer
from lichoscli.core.models.git_repo import GitRepo
from lichoscli.core.services import PackageService

logger = logging.getLogger(__name__)


class SubmoduleCommand(Command):
    """Manage git submodule projects with all packages in a flattened hierarchy"""

    def __init__(self, di_container: DIContainer, args):
        super().__init__(di_container, args)
        self.package_service = di_container.obtain_ref(PackageService)
        self.subcommand = getattr(args, "subcommand", None)
        if self.subcommand == "create":
            self.project_name = args.project_name
            self.output_dir = args.output_dir or "."
        elif self.subcommand == "update":
            self.target_path = Path(args.path).resolve()
            self.push = args.push
    @classmethod
    def add_arguments(cls, sp):
        subparsers = sp.add_subparsers(dest="subcommand", help="submodule operations")

        # Create subcommand
        create_parser = subparsers.add_parser("create", help="create a new submodule project")
        create_parser.add_argument("project_name", help="name of the submodule project to create")
        create_parser.add_argument(
            "--output-dir",
            "-o",
            default=".",
            help="output directory for the project (default: current directory)",
        )
        create_parser.add_argument(
            "--push",
            action="store_true",
            default=False,
            help="push changes to remote repository after creating the project",
        )

        # Update subcommand
        update_parser = subparsers.add_parser("update", help="update existing submodule project")
        update_parser.add_argument("path", help="path to existing submodule project to update")
        update_parser.add_argument(
            "--push",
            action="store_true",
            default=False,
            help="push changes to remote repository after updating",
        )

    def execute(self):
        """Execute the submodule command based on the specified subcommand."""
        if self.subcommand == "create":
            return self._execute_create()
        if self.subcommand == "update":
            return self._execute_update()
        logger.error("Invalid subcommand: %s. Use 'create' or 'update'", self.subcommand)
        return 1

    def _execute_create(self):
        """Execute the create subcommand to create a new submodule project."""
        if not self.project_name:
            logger.error("Project name is required for create subcommand")
            return 1

        # Create project directory
        project_path = Path(self.output_dir) / self.project_name
        if project_path.exists():
            logger.error("Project directory '%s' already exists", project_path)
            logger.error("Please choose a different project name or remove the existing directory")
            return 1

        logger.info("Creating submodule project: %s", project_path)
        project_path.mkdir(parents=True, exist_ok=True)

        # Initialize repository
        initial_branch = self.args.branch
        origin_url = f"git@{self.args.host}:{self.di_container.group_rpath}/{self.project_name}.git"
        
        repo = GitRepo.init(project_path, initial_branch, origin_url)

        # Get packages and add as submodules
        packages = self.package_service.get_packages_by_branch(initial_branch)
        if not packages:
            logger.warning("No packages found to add as submodules")
            return 0

        logger.info("Found %d packages to add as submodules", len(packages))
        added_submodules, failed_submodules = [], []

        for package in sorted(packages, key=lambda p: p.name):
            submodule_path = project_path / package.name
            
            success = repo.add_submodule(
                package.name,
                package.ssh_url_to_repo,
                str(submodule_path.relative_to(project_path)),
                initial_branch,
            )
            (added_submodules if success else failed_submodules).append(package.name)

        if added_submodules:
            # Commit .gitmodules and added submodules
            if not repo.commit("Initial commit: Add all pkg submodules"):
                logger.error("Failed to create initial commit")

        self._log_create_summary(project_path, added_submodules, failed_submodules)
        return self._handle_push_if_requested(repo, project_path, added_submodules, failed_submodules)

    def _execute_update(self):
        """Execute the update subcommand to update an existing submodule project."""
        repo = GitRepo(self.target_path)
        if not repo.is_valid:
            logger.error("Invalid git repository at %s", self.target_path)
            return 1

        if not repo.has_submodules:
            logger.warning(
                "No .gitmodules file found in '%s' - no submodules to update",
                self.target_path,
            )
            return 0

        logger.info("Found git repository with submodules at: %s", self.target_path)

        submodules = repo.submodules
        if not submodules:
            return 0

        updated_names = []
        for submodule in submodules:
            current_sha = submodule.hexsha
            package = self.package_service.get_package(submodule.name)
            
            if not package:
                logger.error("Package '%s' not found in hierarchy", submodule.name)
                continue

            branch = getattr(self.args, "branch", None)
            branch_obj = self.package_service.get_package_branch(package, branch)
            if not branch_obj:
                logger.error("Branch '%s' not found for package '%s'", branch, package.name)
                continue

            latest_sha = branch_obj.commit["id"]

            if current_sha == latest_sha:
                continue

            if repo.update_submodule_commit(submodule.path, latest_sha):
                logger.info(
                    "Updated submodule '%s': %s -> %s",
                    submodule.name,
                    current_sha[:8],
                    latest_sha[:8],
                )
                updated_names.append(submodule.name)
            else:
                logger.error("Failed to update submodule '%s'", submodule.name)

        committed = False
        if updated_names:
            commit_message = f"Update submodules: {', '.join(updated_names)}"
            committed = repo.commit(commit_message)
            if committed:
                logger.info("Committed submodule updates: %s", commit_message)
            else:
                logger.info("No changes detected after submodule updates")

        if committed and self.args.push:
            branch_success = repo.push_branch()
            tags_success = repo.push_tags()
            if not (branch_success and tags_success):
                logger.warning("Failed to push changes to remote repository")
                return 2
        elif committed and not self.args.push:
            logger.info("Changes have been committed locally. Use --push to push to remote repository.")

        logger.info("Submodule update completed for: %s", self.target_path)
        logger.info("Updated: %d submodules", len(updated_names))
        if committed:
            logger.info("Changes have been committed to the repository")
        elif not updated_names:
            logger.info("All submodules were already up to date")
        else:
            logger.info("No changes were committed (repository may be clean)")

        return 0

    def _log_create_summary(self, project_path, added_submodules, failed_submodules):
        """Print a summary of the submodule project creation."""
        logger.info("Submodule project '%s' created successfully!", self.project_name)
        logger.info("Location: %s", project_path)
        logger.info("Added %d submodules", len(added_submodules))

        if failed_submodules:
            logger.warning("Failed to add %d submodules:", len(failed_submodules))
            for name in failed_submodules:
                logger.warning("  - %s", name)

        logger.info("To clone with all submodules:")
        logger.info("  git clone --recursive %s", project_path)
        logger.info("To update all submodules:")
        logger.info("  cd %s", project_path)
        logger.info("  git submodule update --remote --recursive")

    def _handle_push_if_requested(self, repo: GitRepo, project_path, added_submodules, failed_submodules):
        """Handle pushing changes if requested."""
        if not added_submodules:
            return 0 if not failed_submodules else 2

        if self.args.push:
            logger.info("Attempting to push submodule project to remote repository...")
            branch_success = repo.push_branch()
            tags_success = repo.push_tags()
            
            if not (branch_success and tags_success):
                logger.error("Failed to push changes to remote repository")
                logger.error("Please ensure the remote repository exists and you have push permissions:")
                origin_url = f"git@{self.args.host}:{self.di_container.group_rpath}/{self.project_name}.git"
                logger.error("  Remote URL: %s", origin_url)
                logger.error("You can create the repository manually and push later with:")
                logger.error("  cd %s", project_path)
                logger.error(
                    "  git push -u origin %s",
                    getattr(self.args, "branch", None) or "main",
                )
                return 2
        else:
            logger.info("Changes have been committed locally. Use --push to push to remote repository.")
            logger.info("To push manually:")
            logger.info("  cd %s", project_path)
            logger.info("  git push -u origin %s", getattr(self.args, "branch", None) or "main")

        return 0 if not failed_submodules else 2
