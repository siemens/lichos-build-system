import logging
from datetime import datetime
from lichoscli.commands.base import Command
from lichoscli.utils import BuildUtils
from gitlab.exceptions import GitlabError

logger = logging.getLogger(__name__)


class MergerequestCommand(Command):
    """list open merge requests for packages"""

    def __init__(self, pkg_group_handler, args):
        super().__init__(pkg_group_handler, args)
        self.package_name = BuildUtils.get_package_name(args.package) if hasattr(args, 'package') and args.package else None
        self.dump = args.dump if hasattr(args, 'dump') else False

    @classmethod
    def add_arguments(cls, sp):
        sp.add_argument("package", nargs="?", help="package name (optional, if not provided shows MRs for all packages)")

    def execute(self):
        if self.package_name:
            return self.list_package_merge_requests()
        return self.list_all_merge_requests()

    def list_package_merge_requests(self):
        """List merge requests for a specific package"""
        try:
            package = self.pkg_group_handler.get_package(self.package_name)
            if not package:
                print(f"Package '{self.package_name}' not found")
                return 1

            merge_requests = self._get_merge_requests_for_package(package)
            
            if not merge_requests:
                print(f"No open merge requests found for package '{self.package_name}'")
                return 0

            self._display_merge_requests([(package.name, merge_requests)])
            return 0

        except GitlabError as e:
            logger.error("GitLab API error: %s", str(e))
            return 1


    def list_all_merge_requests(self):
        """List merge requests for all packages"""
        try:
            packages = self.pkg_group_handler.get_all_packages()
            
            results = []
            total_mrs = 0
            
            for package in packages:
                try:
                    merge_requests = self._get_merge_requests_for_package(package)
                    if merge_requests:
                        results.append((package.name, merge_requests))
                        total_mrs += len(merge_requests)
                except GitlabError as e:
                    logger.warning("Failed to get merge requests for package %s: %s", package.name, str(e))

            if not results:
                print("No open merge requests found in any package")
                return 0

            print(f"Found {total_mrs} open merge request(s) across {len(results)} package(s):")
            print()
            self._display_merge_requests(results)
            return 0

        except GitlabError as e:
            logger.error("Error listing merge requests: %s", str(e))
            return 1

    def _get_merge_requests_for_package(self, package):
        try:
            return self.pkg_group_handler._get_merge_requests_for_package(package, state="opened", all=True)
        except GitlabError as e:
            logger.debug("Failed to get merge requests for package %s: %s", package.name, str(e))
            return []

    def _display_merge_requests(self, results):
        if self.dump:
            import json
            output = []
            for package_name, merge_requests in results:
                for mr in merge_requests:
                    output.append({
                        "package": package_name,
                        "iid": mr.iid,
                        "title": mr.title,
                        "source_branch": mr.source_branch,
                        "target_branch": mr.target_branch,
                        "created_at": mr.created_at,
                        "web_url": mr.web_url
                    })
            print(json.dumps(output, indent=2))
        else:
            for package_name, merge_requests in results:
                package_obj = self.pkg_group_handler.get_package(package_name)
                display_name = package_name
                if package_obj and package_obj.namespace["full_path"] is not None and package_obj.namespace["full_path"] != self.pkg_group_handler.group_rpath:
                    display_name = package_obj.namespace["path"] + "/" + package_name
                
                if "/" in display_name:
                    display_name = display_name.split("/")[-1]
                
                print(f"[{display_name}] ({len(merge_requests)} MR{'s' if len(merge_requests) > 1 else ''})")
                print("=" * (len(display_name) + 20))
                print()
                
                for i, mr in enumerate(merge_requests):
                    created_date = self._format_date_with_year(mr.created_at)
                    
                    print(f"  +-- MR #{mr.iid} | Created: {created_date}")
                    print(f"  |-- Author: {mr.author['name']}")
                    print(f"  |-- Branches: {mr.source_branch} -> {mr.target_branch}")
                    print(f"  |-- Title: {mr.title}")
                    print(f"  +-- URL: {mr.web_url}")
                    
                    if i < len(merge_requests) - 1:
                        print("  |")
                
                print()  

    def _format_date(self, date_str):
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        except (ValueError, AttributeError):
            return date_str or "-"

    def _format_date_compact(self, date_str):
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%d.%m')
        except (ValueError, AttributeError):
            return date_str or "-"

    def _format_date_with_year(self, date_str):
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%d.%m.%y')
        except (ValueError, AttributeError):
            return date_str or "-"
