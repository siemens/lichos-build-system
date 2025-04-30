#!/usr/bin/python3
import json
import os
import pickle
import sched
import sys
import tempfile
import time
from typing import Any, List, Tuple, Union
from lichoscli import Tool

import argparse
import logging

logger = logging.getLogger(__name__)

def _read_buildinfo(content: str) -> dict:
    """Return the first deb822 paragraph of a buildinfo file keyed by lowercase field name."""
    fields = {}
    key = None
    for line in content.splitlines():
        if line.startswith("-----BEGIN PGP SIGNED MESSAGE-----") or line.startswith("Hash:"):
            continue
        if not line.strip():
            if fields:
                break
            continue
        if line[0] in " \t":
            if key:
                fields[key] += " " + line.strip()
        elif ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower()
            fields[key] = value.strip()
    return fields

class RebuildTool(Tool):
    def __init__(self):
        super().__init__()
        self.state_dir = None
        self.all_summaries = None
        self.last_successful_pipeline_ids = None

    def configure_state_dir(self, args: argparse.Namespace) -> bool:
        if args.state_dir:
            self.state_dir = args.state_dir
            self._import_state_files()
    
    def _import_state_files(self) -> None:
        all_summaries = self._load_pickle('all_summaries.pkl')
        if all_summaries is None:
            self.all_summaries = all_summaries

        last_successful_pipeline_ids = self._load_pickle('last_successful_pipeline_ids.pkl')
        if last_successful_pipeline_ids is None:
            self.last_successful_pipeline_ids = last_successful_pipeline_ids

    def _save_state_files(self) -> None:
        if self.state_dir:
            self._save_pickle('last_successful_pipeline_ids.pkl', self.last_successful_pipeline_ids)
            self._save_pickle('all_summaries.pkl', self.all_summaries)

    def _load_pickle(self, filename: str) -> Union[object, None]:
        """
        Load a pickle file.
        """
        filepath = os.path.join(self.state_dir, filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'rb') as f:
            return pickle.load(f)
        return None
    
    def _save_pickle(self, filename: str, data: Any) -> None:
        """
        Save a pickle file.
        """
        filepath = os.path.join(self.state_dir, filename)
        with open(filepath, 'wb') as f:
            pickle.dump(data, f)
        return None
    
    def _get_latest_successful_pipeline_id(self, args: argparse.Namespace, pkg: dict) -> Union[int, None]:
        if not args.branch:
            branch_name = pkg['default_branch']

        r = self._get("projects/{}/pipelines?ref={}&per_page=1&status=success".format(pkg['id'], branch_name), all_pages=False)
        if r is None:
            return None
        if len(r) == 0:
            return None
        return r[0]['id']
    
    def _collect_all_pipeline_ids(self, args: argparse.Namespace) -> dict:
        pipline_ids = {}
        for pn in sorted(self.packages().keys()):
                p = self.pkg(pn)
                id = self._get_latest_successful_pipeline_id(args, p)
                if id is None:
                    continue
                pipline_ids[p['name']] = id
        return pipline_ids
    
    def _prepare_packages_summaries(self, args: argparse.Namespace):
        # Because the repository structure can change between runs, let’s get it before each run.
        self._refresh_packages()
        # if it does not exist, create it
        if self.all_summaries is None:
            self.all_summaries = {}
            for pn in sorted(self.packages().keys()):
                p = self.pkg(pn)
                self.all_summaries |= self._ctree_package(args, p['path'])
            self.last_successful_pipeline_ids = self._collect_all_pipeline_ids(args)
            self._save_state_files()
        elif self.last_successful_pipeline_ids is not None:
            # if it does not exist, there is no need to check for new pipelines
            return
        else:
            # get latest successful pipeline ids
            latest_successful_pipeline_ids = self._collect_all_pipeline_ids(args)

            # compare last and latest successful pipeline ids
            for p in latest_successful_pipeline_ids:
                # if the pipeline id is unknown or the id is different from the last id, get the new package summary
                if p not in self.last_successful_pipeline_ids or latest_successful_pipeline_ids[p] != self.last_successful_pipeline_ids[p]:
                    pkg = self.pkg(p)
                    self.all_summaries |= self._ctree_package(args, pkg['path'])
            
            self.last_successful_pipeline_ids = latest_successful_pipeline_ids
            self._save_state_files()

    def _ctree(self, all_summaries: dict) -> Tuple[List[str], List[Tuple[str, str, str, str]], dict]:
        rebuild_list = []
        mismatch_list = []

        all_packages = list(all_summaries.keys())
        # dup the binaries
        for pkey in all_packages:
            package = all_summaries[pkey]
            for binary in package['binary']:
                bkey = "{}.{}".format(binary, package['arch'])
                if bkey not in all_summaries:
                    all_summaries[bkey] = package

        for package in all_packages:
            summary = all_summaries[package]
            for dep in summary['bdeps']:
                bdkey = "{}.{}".format(dep[0], summary['arch'])
                if bdkey not in all_summaries:
                    bdkey = "{}.all".format(dep[0])

                if bdkey in all_summaries:
                    if dep[0] == summary['source']:
                        # one package cycle (lex changelog-generator)
                        continue
                    if all_summaries[bdkey]['version'] != dep[1]:
                        rebuild_list.append(package.split('.')[0])
                        mismatch_list.append((package, dep[0], all_summaries[bdkey]['version'], dep[1]))

        logger.debug("Rebuild list: {}".format(rebuild_list))
        logger.debug("Mismatch list: {}".format(mismatch_list))

        return rebuild_list, mismatch_list, all_summaries
                            
    def _ctree_package(self, args: argparse.Namespace, package: str) -> dict:
        tempdir = self._get_job_artifacts(args.branch, package, 'publish', 'success')
        if not tempdir:
            return {}

        summary = {}
        for fn in os.listdir(os.path.join(tempdir.name, 'DEBS')):
            if not fn.endswith('.buildinfo'):
                continue
            with open(os.path.join(tempdir.name, 'DEBS', fn), 'r') as f:
                binfo = _read_buildinfo(f.read())
                bsummary = {'source': binfo['source'].split(' ')[0], 'bdeps': []}
                for dep in binfo.get('installed-build-depends', '').split(','):
                    package, _, version = dep.partition('(')
                    if package.strip():
                        bsummary['bdeps'].append((package.strip().partition(':')[0], version.strip(' =)')))
                bsummary['binary'] = binfo['binary'].split()
                bsummary['version'] = binfo['version']
                archs = set(binfo['architecture'].split())
                archs.discard('source')
                # only take all if it's alone
                archs.discard('all')
                bsummary['arch'] = archs.pop() if archs else 'all'
                summary["{}.{}".format(bsummary['source'], bsummary['arch'])] = bsummary
        return summary

    def do_ctree(self, args: argparse.Namespace) -> bool:
        """
        ctree command to check for outdated build results
        """
        self._prepare_packages_summaries(args)
        _, mismatch_list, _ = self._ctree(self.all_summaries)
        if len(mismatch_list) > 0:
            for missmatch in mismatch_list:
                package, dep, version, dep_version = missmatch
                print("Version mismatch in {}: {}={} vs {}={}".format(package, dep, version, dep, dep_version))
        else:
            print("No version mismatch found")
        return True

    def _buildlist(self, rebuild_list: List[str], all_summaries_extended: dict) -> List[List[str]]:        
        sources = self._extract_sources(all_summaries_extended)
        logger.debug("Sources: %s", json.dumps(sources, indent=2))

        source_dependencies = self._determine_source_dependencies(all_summaries_extended, sources)
        logger.debug("Source dependencies: %s", json.dumps(source_dependencies, indent=2))

        # find all root packages which are not dependencies
        root_packages = self._determine_root_packages(source_dependencies)
        logger.debug("Root packages: %s", root_packages)

        dependency_trees = self._build_trees(root_packages, source_dependencies)
        logger.debug("Dependency trees: %s", json.dumps(dependency_trees, indent=2))

        package_build_paths = self._find_key_paths(dependency_trees, rebuild_list)
        logger.debug("Package build paths: %s", package_build_paths)

        final_build_list = self._merge_path_lists(package_build_paths)
        return final_build_list
        
    def _extract_sources(self, summaries: dict) -> dict:
        sources = {}
        for summary in summaries:
            sources[summary.split('.')[0]] = summaries[summary]['source']
        return sources
    
    def _determine_source_dependencies(self, summaries: dict, sources: dict ) -> dict:
        source_dependencies = {}
        for summary in summaries:
            if source_dependencies.get(summaries[summary]['source']) is not None:
                dep_sources = source_dependencies[summaries[summary]['source']]
            else:
                dep_sources = {}
            for dep in summaries[summary]['bdeps']:
                if dep[0] in sources.keys():
                    dep_sources[sources.get(dep[0])] = {}
            source_dependencies.update({summaries[summary]['source']: dep_sources})
        return source_dependencies

    def _determine_root_packages(self, source_dependencies: dict) -> List[str]:
        return [pkg for pkg in source_dependencies if not any(pkg in deps for deps in source_dependencies.values())]

    def _build_trees(self, root_packages: List[str], source_dependencies: dict) -> dict:
        dependency_trees = {}
        for package in root_packages:
            dependency_trees[package] = None

        for root_package in dependency_trees.keys():
            dependency_trees[root_package] = self._build_tree(root_package, source_dependencies)
        return dependency_trees
    
    def _build_tree(self, package, dependencies):
        if package not in dependencies or not dependencies[package]:
            return {}
        tree = {}
        for dep in dependencies[package]:
            subtree = self._build_tree(dep, dependencies)
            tree[dep] = subtree if subtree else {}
        return tree
    
    def _find_key_paths(self, dictionary: dict, search_terms: Union[str, List[str]], current_path:Union[List, None]=None, results:Union[List, None]=None):
        if not isinstance(search_terms, list):
            search_terms = [search_terms]

        if results is None:
            results = []
        if current_path is None:
            current_path = []

        for key, value in dictionary.items():
            path = current_path + [key]
            
            for term in search_terms:
                if term in str(key):
                    results.append(path[::-1])
                    break
            
            if isinstance(value, dict):
                self._find_key_paths(value, search_terms, path, results)
        
        return results
    
    def _merge_path_lists(self, path_lists: List[List[str]]) -> List[List[str]]:
        max_positions = {}
        predecessors = {}
        
        for path in path_lists:
            for pos, item in enumerate(path):
                max_positions[item] = max(max_positions.get(item, 0), pos)
                
                # Vorgänger-Beziehungen
                if item not in predecessors:
                    predecessors[item] = set()
                predecessors[item].update(path[:pos])
        
        position_map = {}
        for item, pos in max_positions.items():
            if pos not in position_map:
                position_map[pos] = set()
            position_map[pos].add(item)
        
        remaining = set(max_positions.keys())
        
        result = []
        for pos in sorted(position_map.keys()):
            current_group = []
            candidates = position_map[pos].intersection(remaining)
            
            while candidates:
                available = {item for item in candidates 
                            if not predecessors[item].intersection(remaining)}
                
                if not available:
                    break
                
                current_group.extend(sorted(available))
                remaining.difference_update(available)
                candidates.difference_update(available)
                
            if current_group:
                result.append(current_group)
        
        return result
     
    def do_buildlist(self, args: argparse.Namespace) -> bool:
        """
        buildlist command to show the build list for outdated packages
        """
        self._prepare_packages_summaries(args)
        rebuild_list, _ , all_summaries_extended = self._ctree(self.all_summaries)
        with open("all_summaries_extended.json", "w") as f:
            json.dump(all_summaries_extended, f, indent=2)
        current_package_build_status = self._get_current_package_build_status(args)
        with open("current_package_build_status.json", "w") as f:
            json.dump(current_package_build_status, f, indent=2)
        buildlist = self._buildlist(rebuild_list, all_summaries_extended, current_package_build_status)
        print("Build list: {}".format(buildlist))
        return True

    def _trigger_rebuild(self, args: argparse.Namespace):
        non_rebuildable_piplines_states = ['created', 'waiting_for_resource', 'preparing', 'pending', 'running']
        self._prepare_packages_summaries(args)
        rebuild_list, _ , all_summaries_extended = self._ctree(self.all_summaries)
        current_package_build_status = self._get_current_package_build_status(args)
        buildlist = self._buildlist(rebuild_list, all_summaries_extended)
        buildlist_with_pipeline_status = self._generate_build_list_with_buildstatus(buildlist, current_package_build_status)
        if len(buildlist_with_pipeline_status) > 0:
            buildstage = buildlist_with_pipeline_status[0]
            for package in buildstage:
                package_name = list(package.keys())[0]
                package_status = list(package.values())[0]
                if package_status in non_rebuildable_piplines_states:
                    logger.info("Package build for {} is already in progress".format(package_name))
                    continue
                if not args.dry:
                    self._trigger_package(package_name, args.branch)
                else:
                    logger.info("Dry run: would trigger package build for %s", package_name)
        else:
            logger.info("No packages to rebuild")

    def _scheduler(self, args: argparse.Namespace, scheduler: sched.scheduler, end_time: int):
        current_time = time.time()
        if current_time < end_time:
            self._trigger_rebuild(args)
            
            scheduler.enterabs(
                time=current_time + (args.interval * 60),
                priority=1,
                action=self._scheduler,
                argument=(args, scheduler, end_time)
        )
            
    def _generate_build_list_with_buildstatus(self, buildlist: List[List[str]], current_package_build_status: dict):
        build_list_with_buildstatus = []
        for pkg_list in buildlist:
            pkg_status_combined = []
            for pkg in pkg_list:
                if pkg in current_package_build_status:
                    pkg_status_combined.append({pkg: current_package_build_status[pkg]})
                else:
                    pkg_status_combined.append({pkg: None})
            build_list_with_buildstatus.append(pkg_status_combined)
        return build_list_with_buildstatus
    
    def _get_current_package_build_status(self, args: argparse.Namespace) -> dict:
        package_build_status = {}
        for pn in sorted(self.packages().keys()):
            p = self.pkg(pn)
            r = self._get_pkg_pipeline_status(args, p)
            if r is None:
                continue
            if len(r) == 0:
                continue
            r = r[0]
            package_build_status[p['name']] = r['status']
        return package_build_status
    
    def do_scheduler(self, args: argparse.Namespace) -> bool:
        """
        scheduler command to start the scheduler
        """
        if args.run_once:
            logger.info("Running scheduler once")
            self._trigger_rebuild(args)
            return True
        else:
            logger.info("Starting scheduler")
            scheduler = sched.scheduler(time.time, time.sleep)
            start_time = time.time()
            end_time = start_time + (args.duration * 60)
            self._scheduler(args, scheduler, end_time)
            scheduler.run()
            return True
    
    
def main(args: argparse.Namespace) -> int:
    logger.info("main")
    if args.branch:
        logger.info("branch: %s", args.branch)

    rebuildTool = RebuildTool()
    if not rebuildTool.configure(args):
        return 1
    rebuildTool.configure_state_dir(args)

    f = getattr(rebuildTool, 'do_{}'.format(args.command.replace('-', '_')), None)
    if f is None:
        logger.error("%s() not implemented", args.command)
        return 1

    r = f(args)
    if r is None:
        return 0
    if isinstance(r, bool):
        return not r
    if isinstance(r, int):
        return r

    raise Exception("Invalid return type from handler function")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
                    description="tool to manage package builds in gitlab")
    parser.add_argument("--dry", action="store_true", help="dry run")
    parser.add_argument("--host", help="gitlab host name")
    parser.add_argument("--project", help="project to work with. Must end in /pkg")
    parser.add_argument("--debug", action="store_true", help="debug output")
    parser.add_argument("--verbose", "-v", action="store_true", help="verbose")
    parser.add_argument("--branch", help="branch name for some commands")
    parser.add_argument("--state-dir", default=None, help="directory for state files")

    subparsers = parser.add_subparsers(dest="command", title="Commands")

    sp = subparsers.add_parser("ctree", help="show outdated packages")

    sp = subparsers.add_parser("buildlist", help="show build list")

    sp = subparsers.add_parser("scheduler", help="start scheduler")
    sp.add_argument("--run-once", help="run scheduler once", action="store_true")
    sp.add_argument("--duration", type=int, default=55, help="execution time in minutes")
    sp.add_argument("--interval", type=int, default=5, help="interval in minutes")

    parsed_args = parser.parse_args()

    if not getattr(parsed_args, 'command', None):
        parser.print_help()
        sys.exit(1)

    if parsed_args.debug:
        level = logging.DEBUG
    elif parsed_args.verbose:
        level = logging.INFO
    else:
        level = None

    logging.basicConfig(level=level, format='[%(levelname).1s] %(message)s')

    sys.exit(main(parsed_args))

# vim: sw=4 et