import logging
from functools import wraps
import os
import subprocess
import tempfile
import concurrent.futures

from lichoscli.utils import CIConfigUtils, CI_PKG, GitUtils

logger = logging.getLogger(__name__)


def package_cache(method):

    @wraps(method)
    def wrapper(self, package_name, *args, **kwargs):
        if package_name in self._packages_cache:
            return self._packages_cache[package_name]

        result = method(self, package_name, *args, **kwargs)

        if result is not None:
            self._packages_cache[package_name] = result

        return result

    return wrapper


class PkgGroupHandler:

    def __init__(self, group_rpath: str, gitlab):
        self.group_rpath = group_rpath
        self.gitlab = gitlab
        self.group_id = gitlab.groups.get(group_rpath).id
        self._packages_cache = {}
        self._all_packages_cache = None
        self._project_groups_cache = None
        self._subgroups_cache = None
        self._namespace_ids_cache = None
        self._pipelines_cache = {}

    def _collect_packages(self):
        if self._project_groups_cache is not None:
            return self._project_groups_cache
            
        group = self.gitlab.groups.get(self.group_rpath)
        
        logger.debug("Fetching subgroups for main group %s", self.group_rpath)
        subgroups = group.subgroups.list(all=True)
        self._subgroups_cache = subgroups
        
        subgroup_ids = {subgroup.id: subgroup for subgroup in subgroups}
        subgroup_ids[self.group_id] = group
        
        logger.debug("Fetching ALL projects for main group %s (including subgroups)", self.group_rpath)
        project_groups = self.gitlab.groups.get(self.group_id).projects.list(include_subgroups=True, all=True)
        
        self._project_groups_cache = project_groups
        return project_groups

    def get_all_packages(self):
        if self._all_packages_cache is not None:
            logger.debug("Using cached packages")
            return self._all_packages_cache

        project_groups = self._collect_packages()
    
        packages = []
        for project_group in project_groups:
            package = project_group
            self._packages_cache[package.name] = package
            packages.append(package)
        self._all_packages_cache = packages
        return packages

    def pretty_format_ci_path(self, package):
        result = package.ci_config_path
        if not package.ci_config_path or package.ci_config_path == '.gitlab-ci.yml':
            result = 'local'
        else:
            parsed = CIConfigUtils.parse_ci_config_path(package.ci_config_path)
            if parsed:
                group_matches = parsed.group == GitUtils.get_main_group(package.namespace['full_path'])
                parent_match = False
                if not group_matches:
                    p = self.get_package(CI_PKG)
                    if p and hasattr(p, 'forked_from_project'):
                        if p.forked_from_project['namespace']['full_path'] == parsed.group:
                            group_matches = True
                            parent_match = True
                if parsed and group_matches and parsed.pkg == CI_PKG:
                    result = parsed.name
                    if parent_match:
                        result += '*'
                    if parsed.branch:
                        result += ":" + parsed.branch

        logger.debug("%s: %s -> %s", package.name, package.ci_config_path, result)
        return result

    @package_cache
    def get_package(self, package_name, full_details=False):
        try:
            if package_name not in self._packages_cache:
                if self._all_packages_cache is None:
                    self.get_all_packages()
            package = self._packages_cache[package_name]
            
            if full_details and (not hasattr(package, 'pipelines') or package.pipelines is None):
                logger.debug("Getting full project details for %s", package_name)
                package = self.gitlab.projects.get(package.id)
                self._packages_cache[package_name] = package
        
            return package

        except Exception as e:
            logger.error("Error getting project '%s': %s", package_name, str(e))
            return None
            
    def _get_valid_namespace_ids(self):
        if self._namespace_ids_cache is None:
            self._namespace_ids_cache = [self.group_id]

            if self._subgroups_cache is None:
                self._collect_packages()

            if self._subgroups_cache:
                for subgroup in self._subgroups_cache:
                    self._namespace_ids_cache.append(subgroup.id)
                    
        return self._namespace_ids_cache

    def update_package(
        self,
        package_name: str,
        ci_config_path: str|None = None,
        branch: str = None,
        access_level: str = "enabled",
    ):
        pkg = self.get_package(package_name, full_details=True)

        if not pkg:
            logger.error("Package %s not found.", package_name)
            return None
        if ci_config_path:
            pkg.ci_config_path = ci_config_path
        if branch:
            pkg.default_branch = branch
        pkg.builds_access_level = access_level

        try:
            pkg.save()
            logger.info("Package %s updated successfully.", package_name)
            return pkg
        except Exception as e:
            logger.error("Failed to update package %s: %s", package_name, str(e))
            return None

    def add_package(
        self,
        package_name: str,
        branch: str,
        package_type: str,
        subgroup: str,
        access_level: str = "enabled",
    ):

        if subgroup:
            subgroup = self.gitlab.groups.get(f"{self.group_rpath}/{subgroup}")
            namespace_id = subgroup.id
        else:
            namespace_id = self.group_id

        ci_config_path = CIConfigUtils.get_ci_path(
            self.group_rpath, ci_typ=package_type
        )

        project = self.gitlab.projects.create(
            {
                "name": package_name,
                "namespace_id": namespace_id,
                "ci_config_path": ci_config_path,
                "default_branch": branch,
                "builds_access_level": access_level,
            }
        )
        if project:
            return project

    def get_latest_pipeline(self, package_name, branch: str | None = None, use_cache_only=False):
        cache_key = f"{package_name}:{branch or 'default'}"
        if cache_key in self._pipelines_cache:
            logger.debug("Pipeline cache hit for %s", cache_key)
            return self._pipelines_cache[cache_key]

        if use_cache_only:
            return None

        pkg = self.get_package(package_name)
        if not pkg:
            return None

        # Ensure we have full project details for pipeline access
        if not hasattr(pkg, 'pipelines') or pkg.pipelines is None:
            logger.debug("Getting full project details for %s", package_name)
            pkg = self.gitlab.projects.get(pkg.id)
            self._packages_cache[package_name] = pkg

        pipelines = pkg.pipelines.list(
            ref=branch if branch else pkg.default_branch,
            per_page=1, order_by="id", sort="desc", get_all=False)

        result = pipelines[0] if pipelines else None

        self._pipelines_cache[cache_key] = result
        return result

    def get_all_pipelines_status(self, max_workers=10, branch: str | None = None):
        packages = self.get_all_packages()
        pipeline_statuses = {}

        uncached_packages = []
        for package in packages:
            cached_pipeline = self.get_latest_pipeline(package.name, branch=branch, use_cache_only=True)
            if cached_pipeline is not None:
                logger.debug("Pipeline cache hit for %s", package.name)
                pipeline_statuses[package.name] = cached_pipeline
            else:
                uncached_packages.append(package)

        if uncached_packages:
            logger.debug("Fetching pipeline status for %s packages in parallel", len(uncached_packages))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(self.get_latest_pipeline, package.name, branch=branch)
                    for package in uncached_packages
                ]
                
                for future, package in zip(concurrent.futures.as_completed(futures), uncached_packages):
                    try:
                        pipeline = future.result()
                        pipeline_statuses[package.name] = pipeline
                    except Exception as e:
                        logger.error("Error processing pipeline fetch for %s: %s", package.name, str(e))
                        pipeline_statuses[package.name] = None
        
        return pipeline_statuses

    def get_job_by_name(self, pkg, jobname: str):
        """Find the specified job in the latest pipeline."""
        latest_pipeline = self.get_latest_pipeline(pkg.name)
        if latest_pipeline is None:
            logger.error(
                "No pipeline found for job %s in package %s.", jobname, pkg.name
            )
            return None

        pipeline_jobs = latest_pipeline.jobs.list(all=True)
        if not pipeline_jobs:
            logger.error(
                "No jobs found in the latest pipeline for package %s.", pkg.name
            )
            return None

        job = next((j for j in pipeline_jobs if j.name == jobname), None)
        if job is None:
            logger.error("Job %s not found in package %s.", jobname, pkg.name)

        return job

    def get_package_variables(self, package):
        if not hasattr(package, 'variables') or package.variables is None:
            logger.debug("Getting full project details for package %s to access variables", package.name)
            package = self.gitlab.projects.get(package.id)
        variables = package.variables.list(all=True)
        variables_dict = {}
        for v in variables:
            variables_dict[v.key] = v.value
        return variables_dict

    @staticmethod
    def get_job_artifacts(
        package, branch_name: str, job_name: str
    ) -> tempfile.TemporaryDirectory | None:
        """
        Get job artifacts using gitlab module.
        Returns a TemporaryDirectory containing the extracted artifacts or None if unsuccessful.
        """
        try:
            logger.debug(
                "Attempting to download artifacts for job: %s, branch: %s",
                job_name,
                branch_name,
            )

            temp_dir_obj = tempfile.TemporaryDirectory(dir="/tmp")
            temp_dir = temp_dir_obj.name

            branch_name = branch_name or package.default_branch

            try:
                # First attempt with the branch name directly
                downloaded = PkgGroupHandler.get_artifacts_by_branch(
                    package, branch_name, job_name
                )
                if downloaded is None:
                    # If branch name fails, try to find corresponding merge request
                    logger.debug(
                        "Direct branch download failed, trying via merge requests"
                    )
                    downloaded = PkgGroupHandler.get_artifacts_by_mr(
                        package, branch_name, job_name
                    )
            except Exception as e:
                logger.error(
                    "Error downloading artifacts for job: %s, branch: %s: %s",
                    job_name,
                    branch_name,
                    str(e),
                )
                temp_dir_obj.cleanup()
                return None

            if downloaded is None:
                logger.error(
                    "Failed to download artifacts for job: %s, branch: %s",
                    job_name,
                    branch_name,
                )
                temp_dir_obj.cleanup()
                return None

            # Sanitize branch name to avoid path issues (replace slashes with underscores)
            safe_branch_name = branch_name.replace("/", "_").replace("\\", "_")
            zipfn = os.path.join(temp_dir, f"{job_name}_{safe_branch_name}.zip")

            try:
                with open(zipfn, "wb") as f:
                    f.write(downloaded)
                logger.debug("Successfully wrote artifact to %s", zipfn)
            except Exception as e:
                logger.error("Failed to write artifact data to file: %s", str(e))
                temp_dir_obj.cleanup()
                return None

            if os.path.getsize(zipfn) == 0:
                print("Warning: Downloaded artifact file is empty")
                temp_dir_obj.cleanup()
                return None

            subprocess.run(["unzip", "-qq", "-bo", zipfn, "-d", temp_dir], check=True)
            os.unlink(zipfn)

            return temp_dir_obj
        except Exception:
            print(
                f"Error processing artifacts: branch={branch_name}, job={job_name} could have no artifacts"
            )
            if "temp_dir_obj" in locals():
                temp_dir_obj.cleanup()
            return None

    @staticmethod
    def get_artifacts_by_branch(
        package, branch_name: str, job_name: str
    ) -> bytes | None:
        """
        Get job artifacts directly using branch name.
        Returns downloaded artifact data or None if unsuccessful.
        """
        try:
            return package.artifacts.download(job=job_name, ref_name=branch_name)
        except Exception:
            logger.debug(
                "Failed to download artifacts directly for job: %s, branch: %s",
                job_name,
                branch_name,
            )
            return None

    @staticmethod
    def get_artifacts_by_mr(package, branch_name: str, job_name: str) -> bytes | None:
        """
        Get job artifacts using merge request.
        Returns downloaded artifact data or None if unsuccessful.
        """
        try:
            mrs = package.mergerequests.list(state="opened", source_branch=branch_name)
            if mrs:
                mr_iid = mrs[0].iid
                logger.debug("Found merge request %s for branch %s", mr_iid, branch_name)
                return package.artifacts.download(
                    job=job_name, ref_name=f"refs/merge-requests/{mr_iid}/head"
                )
            else:
                logger.debug("No merge request found for branch %s", branch_name)
                return None
        except Exception as e:
            logger.debug(
                "Failed to download artifacts via merge request for job: %s, branch: %s: %s",
                job_name,
                branch_name,
                str(e),
            )
            return None

    def trigger_package_build(self, package, branch_name: str = None):
        if branch_name is None:
            branch_name = package.default_branch
        try:
            package.pipelines.create({'ref': branch_name})
        except Exception as e:
            logger.error(
                "Failed to trigger build for package %s on branch %s: %s",
                package.name,
                branch_name,
                str(e),
            )
            return 1
        return 0

    def _refresh_packages(self):
        """
        Clear the package cache to force fresh data retrieval
        """
        self._packages_cache = {}
        self._all_packages_cache = None
        self._project_groups_cache = None
        self._subgroups_cache = None
        self._namespace_ids_cache = None
        self._pipelines_cache = {}
