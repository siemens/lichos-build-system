import logging
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List

from gitlab import GitlabError
from gitlab.v4.objects import Project

from lichoscli.utils import CIConfigUtils, CI_PKG, GitUtils

logger = logging.getLogger(__name__)


class PkgGroupHandler:

    def __init__(self, group_rpath: str, gitlab):
        self.group_rpath = group_rpath
        self.gitlab = gitlab
        self.group_id = gitlab.groups.get(group_rpath).id
        self._packages_cache: Dict[str, Project] = {}

    def _fetch_all_projects(self) -> List[Project]:
        """Fetch all projects from GitLab API."""
        group = self.gitlab.groups.get(self.group_rpath)
        logger.debug("Fetching ALL projects for group %s (including subgroups)", self.group_rpath)
        projects = group.projects.list(include_subgroups=True, all=True)
        full_projects = []
    
        def fetch_project_details(project):
            """Fetch full details for a single project."""
            try:
                full_project = self.gitlab.projects.get(project.id)
                logger.debug("Fetched full details for package: %s", full_project.name)
                return full_project
            except GitlabError as e:
                logger.error("Error getting full details for %s: %s", project.name, str(e))
                return project 
        
        max_workers = min(10, len(projects))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_project = {executor.submit(fetch_project_details, project): project 
                               for project in projects}
            for future in as_completed(future_to_project):
                try:
                    full_project = future.result()
                    full_projects.append(full_project)
                except Exception as e:
                    project = future_to_project[future]
                    logger.error("Unexpected error fetching project %s: %s", project.name, str(e))
                    full_projects.append(project)
        return full_projects

    def _populate_cache(self):
        if self._packages_cache:
            return 
            
        logger.debug("Populating package cache")
        projects = self._fetch_all_projects()
        
        for project in projects:
            self._packages_cache[project.name] = project
        
        logger.debug("Cached %d packages", len(self._packages_cache))

    def get_package(self, package_name: str) -> Optional[Project]:
        if package_name in self._packages_cache:
            logger.debug("Cache hit for package: %s", package_name)
            return self._packages_cache[package_name]
        
        try:
            logger.debug("Fetching package details for: %s", package_name)
            group = self.gitlab.groups.get(self.group_rpath)
            projects = group.projects.list(search=package_name, include_subgroups=True)
        
            for project in projects:
                if project.name == package_name:
                    full_project = self.gitlab.projects.get(project.id)
                    self._packages_cache[package_name] = full_project
                    logger.debug("Cached package: %s", package_name)
                    return full_project
            
            logger.debug("Package %s not found", package_name)
            return None
        except GitlabError as e:
            logger.error("Error fetching package %s: %s", package_name, str(e))
            return None

    def get_all_packages(self) -> List[Project]:
        """Get all packages, using cache when possible."""
        self._populate_cache()
        return list(self._packages_cache.values())

    def _invalidate_cache(self):
        logger.debug("Invalidating package cache")
        self._packages_cache.clear()

    def pretty_format_ci_path(self, package: Project):
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

    def update_package(
        self,
        package_name: str,
        ci_config_path: Optional[str] = None,
        branch: Optional[str] = None,
        access_level: str = "enabled",
    ):
        pkg = self.get_package(package_name)

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
            self._invalidate_cache()
            logger.info("Package %s updated successfully.", package_name)
            return pkg
        except GitlabError as e:
            logger.error("Failed to update package %s: %s", package_name, str(e))
            return None

    @staticmethod
    def _get_merge_requests_for_package(package: Project, branch_name: str = None, state: str = "opened", all: bool = False) -> List:
        try:
            filters = {"state": state}
            if branch_name:
                filters["source_branch"] = branch_name
            if all:
                filters["all"] = all
                
            mrs = package.mergerequests.list(**filters)
            logger.debug("Found %d merge requests for package %s with filters: %s", 
                        len(mrs), package.name, filters)
            return mrs
        except GitlabError as e:
            logger.error("Failed to fetch merge requests for package %s: %s", 
                        package.name, str(e))
            return []

    def _get_subgroup_namespace_id(self, subgroup: str) -> Optional[int]:
        """Get namespace ID for a subgroup."""
        if not subgroup:
            return self.group_id
            
        try:
            subgroup_obj = self.gitlab.groups.get(f"{self.group_rpath}/{subgroup}")
            return subgroup_obj.id
        except GitlabError as e:
            logger.error("Failed to get subgroup %s: %s", subgroup, str(e))
            return None

    def add_package(
        self,
        package_name: str,
        branch: str,
        package_type: str,
        subgroup: str,
        access_level: str = "enabled",
    ):
        namespace_id = self._get_subgroup_namespace_id(subgroup)
        if namespace_id is None:
            logger.error("Failed to get namespace ID for subgroup: %s", subgroup)
            return None

        ci_config_path = CIConfigUtils.get_ci_path(
            self.group_rpath, ci_typ=package_type
        )

        try:
            project = self.gitlab.projects.create(
                {
                    "name": package_name,
                    "namespace_id": namespace_id,
                    "ci_config_path": ci_config_path,
                    "default_branch": branch,
                    "builds_access_level": access_level,
                }
            )
            # Invalidate cache since we added new data
            self._invalidate_cache()
            return project
        except GitlabError as e:
            logger.error("Failed to create package %s: %s", package_name, str(e))
            return None

    def get_latest_pipeline(self, package: Project, branch: str = None):
        """Get the latest pipeline for a package branch."""
        target_branch = branch if branch else package.default_branch

        try:
            pipelines = package.pipelines.list(
                ref=target_branch,
                per_page=1, order_by="id", sort="desc", get_all=False)
            return pipelines[0] if pipelines else None
        except GitlabError as e:
            logger.error("Failed to get pipeline for %s on branch %s: %s", 
                        package.name, target_branch, str(e))
            return None

    def get_job_by_name(self, pkg: Project, jobname: str):
        """Find the specified job in the latest pipeline."""
        latest_pipeline = self.get_latest_pipeline(pkg)
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

    def get_package_variables(self, package: Project):
        try:
            variables = package.variables.list(all=True)
            variables_dict = {}
            for v in variables:
                variables_dict[v.key] = v.value
            return variables_dict
        except GitlabError as e:
            if e.response_code == 403:
                logger.warning("No access to package variables for %s (403 Forbidden). Using empty variables.", package.name)
                return {}
            logger.error("Failed to get package variables for %s: %s", package.name, e)
            raise

    def get_job_artifacts(self, package: Project, branch_name: str, job_name: str) -> tempfile.TemporaryDirectory | None:
        """
        Get job artifacts using gitlab module.
        Returns a TemporaryDirectory containing the extracted artifacts or None if unsuccessful.
        """
        temp_dir_obj = None
        try:
            logger.debug(
                "Attempting to download artifacts for job: %s, branch: %s, project: %s",
                job_name, branch_name, package.name
            )

            temp_dir_obj = tempfile.TemporaryDirectory(dir="/tmp")
            temp_dir = temp_dir_obj.name
            branch_name = branch_name or package.default_branch

            downloaded = self._try_download_artifacts(package, branch_name, job_name)
            if downloaded is None:
                logger.error("Failed to download artifacts for job: %s, branch: %s", job_name, branch_name)
                return None

            safe_branch_name = branch_name.replace("/", "_").replace("\\", "_")
            zipfn = os.path.join(temp_dir, f"{job_name}_{safe_branch_name}.zip")

            with open(zipfn, "wb") as f:
                f.write(downloaded)
            logger.debug("Successfully wrote artifact to %s", zipfn)

            if os.path.getsize(zipfn) == 0:
                logger.error("Downloaded artifact file is empty for job: %s", job_name)
                return None

            subprocess.run(["unzip", "-qq", "-bo", zipfn, "-d", temp_dir], check=True)
            os.unlink(zipfn)

            return temp_dir_obj
        except GitlabError as e:
            logger.error(
                "Error processing artifacts: branch=%s, job=%s - %s",
                branch_name, job_name, str(e)
            )
            return None
        finally:
            if temp_dir_obj is not None and 'downloaded' not in locals():
                temp_dir_obj.cleanup()

    def _try_download_artifacts(self, package: Project, branch_name, job_name):
        """Try different methods to download artifacts."""
        try:
            # Method 1: Try via job ID first
            job_id = self.get_job_id(package, branch_name, job_name)
            if job_id is not None:
                logger.debug("Job found with ID: %s", job_id)
                downloaded = PkgGroupHandler.get_artifacts_by_job_id(package, job_id)
                if downloaded is not None:
                    return downloaded
            # Method 2: Try via merge request
            logger.debug("Job ID download failed, trying via merge requests")
            downloaded = PkgGroupHandler.get_artifacts_by_mr(package, branch_name, job_name)
            if downloaded is not None:
                return downloaded
            logger.debug("Merge request download failed")

        except GitlabError as e:
            logger.error(
                "Error downloading artifacts for job: %s, branch: %s: %s",
                job_name, branch_name, str(e)
            )
            return None

    @staticmethod
    def get_artifacts_by_mr(package: Project, branch_name: str, job_name: str) -> bytes | None:
        """
        Get job artifacts using merge request.
        Returns downloaded artifact data or None if unsuccessful.
        """
        try:
            logger.debug(
                "Searching for merge requests with source branch: %s",
                branch_name,
            )
            mrs = PkgGroupHandler._get_merge_requests_for_package(package, branch_name=branch_name, state="opened")
            if mrs:
                mr_iid = mrs[0].iid
                logger.debug("Found merge request %s for branch %s", mr_iid, branch_name)
                result = package.artifacts.download(
                    job=job_name, ref_name=f"refs/merge-requests/{mr_iid}/head")
                return result
            logger.debug("No merge requests found for branch: %s", branch_name)
            return None
        except GitlabError as e:
            logger.debug(
                "Failed to download artifacts via merge request for job: %s, branch: %s: %s",
                job_name,
                branch_name,
                str(e),
            )
            return None

    @staticmethod
    def get_artifacts_by_job_id(package: Project, job_id: int) -> bytes | None:
        try:
            logger.debug("Attempting to download artifacts using job ID: %s", job_id)
            if not (job := package.jobs.get(job_id)):
                logger.debug("Job %s not found", job_id)
                return None
            result = job.artifacts()
            logger.debug("Downloaded %d bytes using job ID: %s", len(result), job_id)
            return result
        except GitlabError as e:
            logger.debug("Failed to download artifacts using job ID %s: %s", job_id, str(e))
            return None

    def trigger_package_build(self, package: Project, branch_name=None):
        if branch_name is None:
            branch_name = package.default_branch

        mr_info = None
        if branch_name != package.default_branch:
            try:
                mrs = PkgGroupHandler._get_merge_requests_for_package(package, branch_name=branch_name, state="opened")
                if mrs:
                    mr_info = mrs[0]
                    logger.debug("Found merge request %s for branch %s", mr_info.iid, branch_name)
            except GitlabError as e:
                logger.debug("Error checking for merge request on branch %s: %s", branch_name, str(e))

        try:
            if mr_info:
                mr_info.pipelines.create({'ref': branch_name})
                print("Successfully triggered build for {} on MR !{} (branch {}): {}".format(
                    package.name, mr_info.iid, branch_name, mr_info.web_url))
                return 0
            else:
                package.pipelines.create({'ref': branch_name})
                print("Successfully triggered build for {} on branch {}: {}/-/pipelines".format(
                    package.name, branch_name, package.web_url))
                return 0

        except GitlabError as e:
            logger.error("Failed to trigger build for %s on branch %s: %s",
                        package.name, branch_name, str(e))
            return 1

    def extract_log_from_job(self, package: Project, job_name: str) -> Optional[str]:
        try:
            job = self.get_job_by_name(package, job_name)
            if not job:
                logger.warning("Job %s not found for package %s", job_name, package.name)
                return None
                
            full_job = package.jobs.get(job.id)
            trace = full_job.trace()

            if trace:
                log_text = trace.decode('utf-8', errors='replace') if isinstance(trace, bytes) else trace
                return log_text
            else:
                logger.debug("No trace available for job %s", job_name)
                return None
                
        except GitlabError as e:
            logger.warning("Error extracting log from job %s: %s", job_name, str(e))
            return None

    def get_job_id(self, package: Project, branch_name: str, job_name: str):
        try:
            latest_pipeline = self.get_latest_pipeline(package, branch=branch_name)

            if not latest_pipeline:
                logger.debug("No pipeline found for branch: %s", branch_name)
                return None

            jobs = latest_pipeline.jobs.list(all=True)

            for job in jobs:
                job = next((j for j in jobs if j.name == job_name), None)
                if job:
                    logger.debug(
                        "Job '%s' found - ID: %s, status: %s",
                        job_name,
                        job.id,
                        job.status,
                    )
                    return job.id

            logger.debug("Job '%s' not found in pipeline", job_name)
            return None

        except GitlabError as e:
            logger.debug("Error getting job ID: %s", str(e))
            return None
