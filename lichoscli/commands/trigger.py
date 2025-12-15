import logging

from lichoscli.commands.base import Command
from lichoscli.core.services import PackageService
from lichoscli.utils import BuildUtils

logger = logging.getLogger(__name__)


class TriggerCommand(Command):
    """Trigger package build or retrigger specific job from latest pipeline"""

    def __init__(self, di_container, args):
        super().__init__(di_container, args)
        self.package_name = BuildUtils.get_package_name(args.package) if args.package else None
        self.all_packages = args.all
        self.job_name = args.job
        self.branch = args.branch
        self.package_service = di_container.obtain_ref(PackageService)

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="some package name")
        sp.add_argument("job", nargs="?", help="specific job name to retrigger from latest pipeline")
        sp.add_argument("--all", action="store_true", help="trigger all packages")

    def validate_args(self) -> None:
        """Validate command-specific arguments."""
        if self.job_name and not self.package_name:
            raise ValueError("Job name specified but package name is missing. Usage: lichoscli trigger <package> <job>")

    def execute(self):
        if self.package_name and self.job_name:
            return self._retrigger_job()

        if self.package_name:
            return self._trigger_single_package()

        if self.all_packages:
            return self._trigger_all_packages()

        logger.error("Please specify a package or use --all to trigger all packages.")
        return 1

    def _retrigger_job(self):
        """Retrigger a specific job from the latest pipeline."""
        assert self.package_name is not None
        assert self.job_name is not None
        
        package = self.package_service.get_package(self.package_name)
        
        if package is None:
            logger.error("Package '%s' not found", self.package_name)
            return 1
        
        latest_pipeline = package.pipelines.get_latest(self.branch)
        
        if latest_pipeline is None:
            logger.error("No pipeline found for package %s on branch %s", self.package_name, self.branch)
            return 1
        
        job = latest_pipeline.jobs.get_by_name(self.job_name)
        
        if job is None:
            logger.error("Job '%s' not found in pipeline %s", self.job_name, latest_pipeline.id)
            self._list_available_jobs(latest_pipeline)
            return 1
        
        logger.info(
            "Retriggering job '%s' (status: %s) from pipeline %s",
            job.name,
            job.status,
            latest_pipeline.id,
        )
        
        success = job.retry()
        
        if success:
            self.console.print(
                f"[green]✓[/green] Successfully retriggered job [cyan]{job.name}[/cyan] "
                f"from pipeline {latest_pipeline.id}"
            )
            self.console.print(f"  Job URL: {job.web_url}")
            return 0
        else:
            logger.error("Failed to retrigger job '%s'", job.name)
            return 1
    
    def _list_available_jobs(self, pipeline):
        """List available jobs in the pipeline to help user find the correct job name."""
        jobs = pipeline.jobs.list()
        if jobs:
            self.console.print("\n[bold]Available jobs in this pipeline:[/bold]")
            for job in jobs:
                self.console.print(f"  • {job.name} (stage: {job.stage}, status: {job.status})")
        else:
            logger.warning("No jobs found in pipeline")

    def _trigger_single_package(self):
        """Trigger build for a single specified package."""
        package = self.package_service.get_package(self.package_name)
        
        if package is None:
            logger.error("Package '%s' not found", self.package_name)
            return 1
        
        pipeline = package.pipelines.trigger_build(self.branch)
        if not pipeline:
            logger.error("Failed to trigger pipeline for package %s", self.package_name)
            return 1

        self.console.print(
            f"Successfully triggered pipeline for [cyan]{self.package_name}[/cyan]"
        )
        self.console.print(f"  Pipeline URL: {pipeline.web_url}")
        return 0

    def _trigger_all_packages(self):
        """Trigger builds for all eligible packages."""
        eligible_packages = self._get_eligible_packages()

        if not eligible_packages:
            logger.warning("No eligible packages found for branch %s", self.branch or "default")
            return 0

        logger.info(
            "Triggering builds for %d packages with branch %s",
            len(eligible_packages),
            self.branch or "default",
        )

        return self._execute_builds(eligible_packages)

    def _get_eligible_packages(self):
        """Get list of packages eligible for build triggering."""
        eligible_packages = []

        for package in self.package_service.get_all_packages():
            if not self._is_package_eligible(package):
                continue
            eligible_packages.append(package)

        return eligible_packages

    def _is_package_eligible(self, package):
        """Check if a package is eligible for build triggering."""
        if not package.ci_config_path:
            return False

        if self.branch and not package.has_branch(self.branch):
            logger.debug(
                "Package %s does not have branch %s, skipping",
                package.name,
                self.branch,
            )
            return False

        return True

    def _execute_builds(self, packages):
        """Execute builds for the given list of packages."""
        failed_count = 0

        for package in packages:
            pipeline = package.pipelines.trigger_build(self.branch)
            
            if pipeline:
                self.console.print(
                    f"[green]✓[/green] Triggered pipeline for [cyan]{package.name}[/cyan]: {pipeline.web_url}"
                )
            else:
                failed_count += 1

        if failed_count != 0:
            logger.error("one or more packages failed to trigger build, please check the logs.")

        return failed_count
