#!/usr/bin/python3
# Copyright (c) 2016,2022 Siemens AG
# Copyright (c) 2025 Siemens AG
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import argparse
import logging
import os
import re
import shutil
import sys
import urllib.parse
import json
import subprocess
import configparser
import random
import tempfile
from datetime import datetime
from io import BytesIO
from time import sleep
from zipfile import ZipFile
from collections import namedtuple
from pprint import pprint

import requests
import yaml
import git
from tabulate import tabulate
import textwrap

CI_PKG = '00ci'
CI_DEFAULT_PIPELINE_NAME = "gbp"
CI_TEMPLATE = '{name}.yml@{group}/{pkg}'

logger = logging.getLogger(__name__)

def parse_ci_config_path(path):
    P = namedtuple('P', ['name', 'group', 'pkg', 'branch'])
    r = re.match(r'(?P<name>[^@]+).yml(?:@(?P<group>[^:]*)/(?P<pkg>[^/:]+)(?::(?P<branch>.*))?)?$', path)
    if r is None:
        return None

    return P(r.group("name"), r.group("group"), r.group('pkg'), r.group('branch'))

def assert_package(func):
    def wrapper(self, args):
        if (not args.package and self.package) or args.package == '.':
            args.package = self.package
        if not args.package:
            raise argparse.ArgumentError(None, "Missing package parameter")
        return func(self, args)

    return wrapper

class Tool:
    citemplate = CI_TEMPLATE
    ci_pkg = CI_PKG

    # name -> json struct
    _packages = {}
    token = None
    namespace_id = None

    def configure(self, args) -> bool:
        self.host = args.host
        self.group = args.project
        self.package = None

        glabcfgfn = None
        glabcfg = None

        env_group = os.environ.get('CI_PROJECT_NAMESPACE', None)
        env_token = os.environ.get('PKG_TRIGGER_TOKEN', None)
        env_repository_url = os.environ.get('CI_REPOSITORY_URL', None)

        if env_group and env_token and env_repository_url:
            self.group = env_group
            self.token = env_token
            repository_url = env_repository_url
            if repository_url:
                match = re.search(r'@([^/]+)/', repository_url)
                if match:
                    self.host = match.group(1)
            return True
        
        home = os.path.expanduser('~')
        for p in ('', 'snap/glab/current'):
            glabcfgfn = os.path.join(home, p, ".config/glab-cli/config.yml")
            if os.path.exists(glabcfgfn):
                logger.debug("parsing %s", glabcfgfn)
                with open(glabcfgfn, 'r') as fh:
                    glabcfg = yaml.safe_load(fh)
                    break

        if glabcfg is None:
            logger.error("Failed to parse gitlab config. Please create one")
            return False

        if not self.host or not self.group:
            for p in ('.', self.ci_pkg):
                fn = p + "/.git/config"
                if os.path.exists(fn):
                    config = configparser.ConfigParser()
                    config.read(fn)
                    origin = 'remote "origin"'
                    if origin in config:
                        u = config[origin]['url']
                        r = re.match(r'git@(?P<host>[^:]+):(?P<group>.*)/(?P<package>[^/]+)$', u)
                        if r is not None:
                            if not self.host:
                                self.host = r['host']
                                logger.debug("found host %s in %s", self.host, fn)
                            if not self.group:
                                self.group = r['group']
                                logger.debug("found group %s in %s", self.group, fn)
                            if 'package' in args:
                                pkg = r.group('package')
                                if pkg.endswith('.git'):
                                    pkg = pkg[:-4]
                                self.package = pkg
                                logger.debug("found package %s in %s", pkg, fn)
                            break

        if not self.host and 'host' in glabcfg:
            self.host = glabcfg['host']
            logger.debug("got host %s from gitlab config", self.host)

        if not self.host and not self.group:
            logger.error("please specify host and project")
            return False

        if not self.host:
            logger.error("please specify host")
            return False

        self.token = glabcfg['hosts'][self.host].get('token')
        if not self.token:
            logger.error("missing token in %s", glabcfgfn)
            return False

        if not self.group:
            logger.error("please specify --project")
            if self.host:
                print("Available projects:")
                j = self._get('/search?scope=projects&fields=path_with_namespace&search=pkg/00ci')
                if j:
                    for i in j:
                        p = os.path.split(i['path_with_namespace'])[:-1]
                        print("  " + "/".join(p))

            return False

        return True

    def _head(self, path):
        response = requests.head(
            self.url(path),
            headers={"Authorization": "Bearer {}".format(self.token)},
            allow_redirects=False
        )
        return response

    def _get_response(self, path):
        response = requests.get(
            self.url(path),
            headers={"Authorization": "Bearer {}".format(self.token)},
            allow_redirects=False,
            timeout=100,
        )
        return response

    def _get(self, path, all_pages=True, quiet=False):
        response = requests.get(
            self.url(path),
            headers={"Authorization": "Bearer {}".format(self.token)},
            allow_redirects=False,
            timeout=100,
        )
        if response.status_code == 301:
            new_url = response.headers.get('Location')
            new_api_path = new_url.split(self.GITLAB_API, 1)[1]
            # redirect to new url
            logger.debug("redirect to %s", new_api_path)
            return self._get(new_api_path, all_pages)

        if response.status_code != 200:
            if not quiet:
                logger.error("failed GET %s", path)
            return None

        j = response.json()

        if all_pages:
            l = getattr(response, 'links', None)
            while l and 'next' in l:
                url = l['next']['url']
                response = requests.get(
                    url,
                    headers={"Authorization": "Bearer {}".format(self.token), },
                    allow_redirects=False
                )
                if response.status_code != 200:
                    if not quiet:
                        logger.warning("failed GET %s", url)
                    break

                if isinstance(j, dict):
                    j |= response.json()
                elif isinstance(j, list):
                    j += response.json()
                else:
                    logger.warning("unknown type %s", type(j))

                l = getattr(response, 'links', None)

        return j

    def _put(self, path, data):
        response = requests.put(
            self.url(path),
            headers={"Authorization": "Bearer {}".format(self.token)},
            data=data,
            allow_redirects=False
        )
        if response.status_code != 200:
            logger.error("failed PUT %s: %s", path, response.reason)
            return None

        return response.json()

    def _post(self, path, data=None):
        response = requests.post(
            self.url(path),
            headers={"Authorization": "Bearer {}".format(self.token)},
            data=data,
            allow_redirects=False
        )
        if response.status_code > 299:
            logger.error("failed POST %s: %s", path, response.status_code)
            return None

        return response.json()

    def _delete(self, path):
        response = requests.delete(
            self.url(path),
            headers={"Authorization": "Bearer {}".format(self.token)},
            allow_redirects=False
        )
        if response.status_code > 299:
            logger.error("failed DELETE %s: %s", path, response.status_code)
            return None

        return response

    def pipeline(self, name = CI_DEFAULT_PIPELINE_NAME, branch = None):
        ci = self.citemplate.format(name=name, group=self.group, pkg=self.ci_pkg)
        if branch:
            ci += ':' + branch
        return ci

    def pretty_format_enabled(self, ci):
        parsed = parse_ci_config_path(ci)
        if parsed is None:
            return ci
        group_matches = parsed.group == self.group
        parent_match = False
        if not group_matches:
            p = self.pkg(CI_PKG)
            if 'forked_from_project' in p:
                if p['forked_from_project']['namespace']['full_path'] == parsed.group:
                    group_matches = True
                    parent_match = True
        if parsed and group_matches and parsed.pkg == self.ci_pkg:
            ci = parsed.name
            if parent_match:
                ci += '*'
            if parsed.branch:
                ci += ":" + parsed.branch
        elif ci == '.gitlab-ci.yml':
            ci = 'local'

        return ci

    def do_cat(self, args):
        print("cat")
        for f in args.file:
            pprint(f)

    def _refresh_packages(self):
        j = None
        for h in ('groups', 'users'):
            u = '{}/{}/projects?include_subgroups=true'.format(h, urllib.parse.quote(self.group, safe=''))
            r = self._head(u)
            if r.status_code == 404 and '/' not in self.group:
                continue
            if r.status_code == 200:
                j = self._get(u)
                break

        if j is not None:
            for p in j:
                if self.namespace_id is None and 'namespace' in p:
                    self.namespace_id = p['namespace']['id']
                self._packages[p['path']] = p
        logger.debug("{} namespace id {}".format(self.group, self.namespace_id))

    def packages(self) -> dict:
        if not self._packages:
            self._refresh_packages()
        return self._packages

    def pkg(self, name):
        if self._packages and name in self._packages:
            return self._packages[name]

        j = self._get('projects/{}'.format(urllib.parse.quote(os.path.join(self.group, name), safe='')))
        if j is not None:
            if self.namespace_id is None and 'namespace' in j:
                self.namespace_id = j['namespace']['id']
            self._packages[j['path']] = j
            return j

        logger.error("package %s not found in %s:%s", name, self.host, self.group)
        sys.exit(1)

    def do_list(self, args):
        t = [['Name', 'Type', 'Enabled', 'Branch']]
        for pn in sorted(self.packages().keys()):
            p = self.pkg(pn)
            status = None
            ci = self.pretty_format_enabled(p['ci_config_path'])
            on = self.pretty_format_enabled(p['builds_access_level'])
            r = [p['path'], ci, on, p['default_branch']]
            if 'forked_from_project' in p:
                logger.warning("%s forked from %s", pn, p['forked_from_project']['path_with_namespace'])
            t.append(r)
        print(tabulate(t, headers='firstrow'))

    @assert_package
    def do_show(self, args):
        pkg = self.pkg(args.package)
        r = self._get('projects/{}'.format(pkg['id']))
        if r is None:
            return 1

        if args.dump:
            print(json.dumps(r, indent=2))
        elif args.branches:
            r = self._get('projects/{}/repository/branches'.format(pkg['id']))
            if r:
                t = [['SHA', 'Age', 'Protected', 'Name']]
                for b, c, d, prot in [(b['name'], b['commit']['short_id'], b['commit']['committed_date'], b['protected']) for b in r]:
                    n = b
                    if b == pkg['default_branch']:
                        n = "\033[32m{}\033[m".format(b)
                    p = datetime.fromisoformat(d)
                    t.append([c, "{}".format((datetime.now(p.tzinfo) - p).days), prot, n])
                print(tabulate(t, headers='firstrow'))
        else:
            t = [['Setting', 'Value']]
            for i in ('id', 'path', 'ci_config_path', 'builds_access_level', 'default_branch', 'forked'):
                if i == 'forked':
                    if 'forked_from_project' in pkg:
                        t.append([i, pkg['forked_from_project']['path_with_namespace']])
                elif i == 'ci_config_path':
                    t.append([i, self.pretty_format_enabled(pkg['ci_config_path'])])
                else:
                    t.append([i, pkg[i]])
            print(tabulate(t, headers='firstrow'))

        self._load_variables_remote(pkg, print_always=True)

    def _find_job_by_name(self, project, pipeline, name):
        r = self._get('projects/{}/pipelines/{}/jobs'.format(project, pipeline))
        if not r:
            return None

        for j in r:
            if j['name'] == name:
                return j

        return None

    @assert_package
    def do_log(self, args):
        pkg = self.pkg(args.package)
        r = self._get('projects/{}/pipelines?ref={}&per_page=1'.format(pkg['id'], args.branch if args.branch else pkg['default_branch']), all_pages=False)
        if r is None:
            return 1
        r = r[0]

        job = self._find_job_by_name(pkg['id'], r['id'], args.jobname)
        if job is None:
            logger.error("jobs with name %s not found", args.jobname)
            return 1

        if args.wait and job['status'] in ('created', 'pending'):
            sys.stdout.write("Waiting ")
            sys.stdout.flush()
            i = 0
            sp = "/-\\|"
            while job and job['status'] in ('created', 'pending'):
                sleep(3)
                sys.stdout.write('\b')
                sys.stdout.write(sp[i])
                i += 1
                i %= 4
                sys.stdout.flush()
                job = self._get('projects/{}/jobs/{}'.format(pkg['id'], job['id']))
                if not job:
                    return 1
            sys.stdout.write("\n")

        offset = 0
        while True:
            response = self._get_response('projects/{}/jobs/{}/trace'.format(pkg['id'], job['id']))
            if response.status_code != 200:
                logger.error("failed to get log file for job %s", job['id'])
                return 1
            # yeah this method is stupid but also what glab itself does
            written = 0
            for chunk in response.iter_content(chunk_size=128):
                l = len(chunk)
                if written > offset:
                    sys.stdout.write(chunk.decode("utf-8", "backslashreplace"))
                    offset = written
                written += l

            if job['status'] != 'running':
                break

            sleep(3) # glab uses 3 seconds
            job = self._get('projects/{}/jobs/{}'.format(pkg['id'], job['id']))
            if not job:
                return 1

        print("Job {} {}".format(job['id'], job['status']))
    
    def _get_job_artifacts(self, branch_name: str, package: str, job_name: str, pipeline_status: str = None) -> tempfile.TemporaryDirectory|None:
        pkg = self.pkg(package)
        if not branch_name:
            branch_name = pkg['default_branch']

        if pipeline_status:
            pipeline_status_str = "&status={}".format(pipeline_status)
        else:
            pipeline_status_str = ""

        r = self._get("projects/{}/pipelines?ref={}&per_page=1{}".format(pkg['id'], branch_name, pipeline_status_str), all_pages=False)
        if r is None:
            return None
        if len(r) == 0:
            return None
        r = r[0]

        pipeline_jobs = self._get("projects/{}/pipelines/{}/jobs".format(pkg['id'], r['id']))
        if not pipeline_jobs:
            return None
        for job in pipeline_jobs:
            if job['name'] != job_name:
                continue
            response = requests.get(
                self.url("projects/{}/jobs/{}/artifacts".format(pkg['id'], job['id'])),
                headers={"Authorization": "Bearer {}".format(self.token)},
                allow_redirects=False,
                timeout=100,
                )
            if response.status_code != 200:
                logger.error("failed to get artifacts for job %s in %s", job['name'], package)
                return None

            tempdir = tempfile.TemporaryDirectory()

            with ZipFile(BytesIO(response.content)) as z:
                z.extractall(tempdir.name)

            return tempdir
        return None

    def do_status(self, args):
        if not args.package and self.package:
            args.package = self.package
        if args.package and args.package != self.ci_pkg:
            return self._status_package(args)
        return self._status_all(args)
    
    def _get_pkg_pipeline_status(self, args, pkg):
        return self._get('projects/{}/pipelines?ref={}&per_page=1'.format(pkg['id'], args.branch or pkg['default_branch']), all_pages=False)

    def _status_package(self, args):
        pkg = self.pkg(args.package)
        r = self._get_pkg_pipeline_status(args, pkg)
        if r is None:
            return 1
        if len(r) == 0:
            logger.error("No status. No pipeline ever triggered?")
            return 1
        r = r[0]
        if args.dump:
            print(json.dumps(r, indent=2))
        else:
            t = [['Setting', 'Value']]
            for i in ('sha', 'ref', 'status', 'source', 'web_url'):
                t.append([i, r[i]])
            if 'user' in r:
                t.append(["user", r['user']['username']])
            print(tabulate(t, headers='firstrow'))

        # XXX: can't list artifacts here due to missing API
        # https://gitlab.com/gitlab-org/gitlab/-/issues/31448
        pipeline_jobs = self._get('projects/{}/pipelines/{}/jobs'.format(pkg['id'], r['id']))
        if not pipeline_jobs:
            return 1

        print()
        t = [['Id', 'Name', 'Stage', 'Status', 'Started']]
        for job in pipeline_jobs:
            t.append([job[k] for k in ('id', 'name', 'stage', 'status')])
            s = job.get('started_at', None)
            if s:
                s = datetime.fromisoformat(s)
                f = job.get('finished_at', None)
                if f:
                    f = datetime.fromisoformat(f)
                    t[-1].append("{:%Y-%m-%d %H:%M:%S} - {}s".format(s, int((f - s).total_seconds())))
                else:
                    t[-1].append("{:%Y-%m-%d %H:%M:%S}".format(s))
            else:
                t[-1].append("-")
        print(tabulate(t, headers='firstrow'))

    def _status_all(self, args):
        t = [['Name', 'Type', 'Enabled', 'Status', 'Pipeline']]
        for pn in sorted(self.packages().keys()):
            p = self.pkg(pn)
            status = "-"
            d = "-"
            ci = self.pretty_format_enabled(p['ci_config_path'])
            on = self.pretty_format_enabled(p['builds_access_level'])
            r = self._get_pkg_pipeline_status(args, p)
            if 'forked_from_project' in p:
                logger.warning("%s forked from %s", pn, p['forked_from_project']['path_with_namespace'])
            if r is not None and len(r):
                status = r[0]['status']
                u = r[0].get('updated_at', None)
                if u:
                    d = "{:%Y-%m-%d %H:%M:%S}".format(datetime.fromisoformat(u))

            t.append([p['path'], ci, on, status, d])

        print(tabulate(t, headers='firstrow'))

    @assert_package
    def do_enable(self, args):
        pkg = self.pkg(args.package)
        if args.type is None or re.match(r'^[a-z][a-z0-9]+$', args.type) is None:
            logger.error("Pipeline name must be all lowercase letters and digits")
            return False
        cipath = self.pipeline(args.type, args.branch)
        r = self._put('projects/{}'.format(pkg['id']), data={'builds_access_level': 'enabled', 'ci_config_path': cipath})
        return True

    @assert_package
    def do_disable(self, args):
        pkg = self.pkg(args.package)
        r = self._put('projects/{}'.format(pkg['id']), data={'builds_access_level': 'disabled'})

    def do_trigger(self, args):
        if not args.package and self.package:
            args.package = self.package
        if args.all:
            return self._trigger_all(args)

        if args.package and args.package != self.ci_pkg:
            return self._trigger_package(args.package, args.branch)

        logger.error("Please specify package or --all to trigger all")
        return False

    def _trigger_all(self, args):
        packages = sorted(self.packages().keys())
        #random.shuffle(packages)
        for pn in packages:
            if pn == CI_PKG:
                continue
            self._trigger_package(pn, args.branch)

        return True

    def _trigger_package(self, name, branch):
        pkg = self.pkg(name)
        if branch is None:
            branch = pkg['default_branch']
        logger.info("triggering %s in %s", name, branch)
        r = self._post('projects/{}/pipeline?ref={}'.format(pkg['id'], branch))
        if r is None:
            return False
        return True

    @assert_package
    def do_clone(self, args):
        pkg = self.pkg(args.package)
        repo_url = pkg['ssh_url_to_repo']

        if hasattr(args, 'branch') and args.branch:
            try:
                repo = git.Repo.clone_from(repo_url, args.package, branch=args.branch)
            except git.exc.GitCommandError as e:
                logger.warning("Failed to checkout %s: %s", args.branch, e)
                logger.warning("Checkout default branch and create local branch %s", args.branch)
                repo = git.Repo.clone_from(repo_url, args.package)
                repo.git.checkout('-b', args.branch)
        else:
            repo = git.Repo.clone_from(repo_url, args.package)
        
        if 'forked_from_project' in pkg:
            purl = pkg['forked_from_project']['ssh_url_to_repo']
            logger.debug("Adding parent %s", purl)
            parent = repo.create_remote("parent", purl)
            parent.fetch()

        fn = os.path.join(args.package, 'debian/upstream/metadata')
        if os.path.exists(fn):
            logger.debug("Found upstream metadata %s", fn)
            with open(fn, 'r') as fh:
                y = yaml.safe_load(fh)
                if u := y.get('Repository', None):
                    logger.debug("Adding upstream %s", u)
                    upstream = repo.create_remote("upstream", u)
                    upstream.fetch()

        return True

    def _pdiff_local(self, args):
        repo = git.Repo('.')
        assert not repo.bare
        if repo is None:
            logger.error("failed to init git repo")
        if 'parent' not in repo.remotes:
            logger.error('Missing parent repo')
            return False
        parent = repo.remotes.parent
        refname = repo.head.reference

        if str(refname) not in parent.refs:
            pbr = [str(r).split('/', 2)[1] for r in repo.remotes.parent.refs]
            logger.warning("parent repo does not have %s branch, trying %s", refname, pbr[0])
            pref = repo.remotes.parent.refs[pbr[0]]
        else:
            pref = repo.remotes.parent.refs[str(refname)]

        oref = repo.remotes.origin.refs[str(refname)]

        for d in pref.commit.diff(oref.commit, create_patch=True):
            a = "a/{}".format(d.a_blob.path) if d.a_blob else "/dev/null"
            b = "b/{}".format(d.b_blob.path) if d.b_blob else "/dev/null"
            print("diff {} {}".format(oref, pref))
            print("--- {}\n+++ {}".format(a, b))
            print(d.diff.decode('utf-8'))

        return True

    @assert_package
    def do_pdiff(self, args) -> bool:
        if os.path.exists('.git'):
            return self._pdiff_local(args)
        else:
            logger.error("remote pdiff not implemented")

        return True

    @assert_package
    def do_browse(self, args):

        pkg = self.pkg(args.package)

        url = pkg['web_url']
        branch = args.branch
        if branch is None:
            try:
                repo = git.Repo('.')
                branch = str(repo.head.reference)
            except git.exc.InvalidGitRepositoryError:
                logger.error("invalid repo: %s", args.package)
                return 1

        if branch:
            r = self._head('projects/{}/repository/branches/{}'.format(pkg['id'], urllib.parse.quote(branch, safe='')))
            if r.status_code == 204:
                url += "/-/tree/{}".format(branch)
            else:
                logger.warning("branch %s does not exist on server side, showing default branch", branch)

        r = subprocess.run(('xdg-open', url))
        return r.returncode
    
    def _process_variables(self, kind=None, package={}, vars={}, print_always=False):
        r = self._get('groups/{}/variables' if kind == "group" else 'projects/{}/variables'.format(package['namespace']['id'] if kind == "group" else package['id']), quiet=True)
        
        if r:
            t = [['type', 'key', 'value', 'hidden', 'protected', 'masked', 'raw', 'scope', 'description']]

            for v in r:
                vars[v['key']] = v['value']
                if print_always:
                    t.append([v[k] if k != 'value' or v['masked'] == False else '***' for k in ('variable_type', 'key', 'value', 'hidden', 'protected', 'masked', 'raw', 'environment_scope', 'description')])

            if len(t) > 1 and print_always:
                print("Group Variables" if kind == "group" else "Variables")
                print(tabulate(t, headers='firstrow'))

        return vars

    def _load_variables_remote(self, pkg, print_always=False):
        variables = {}

        kind = pkg['namespace']['kind']
        if kind == 'group':
            variables = self._process_variables(kind=kind, package=pkg, vars=variables, print_always=print_always or logger.isEnabledFor(logging.DEBUG))
        else:
            logger.error("Don't know how to handle '{}' variables".format(kind))

        variables = self._process_variables(kind=None, package=pkg, vars=variables, print_always=print_always or logger.isEnabledFor(logging.DEBUG))

        return variables

    def do_create(self, args):
        if not args.branch:
            raise argparse.ArgumentError(None, "need --branch option")
        if '*' in args.branch:
            raise argparse.ArgumentError(None, "branch cannot contain wildcards")
        if not args.package:
            raise argparse.ArgumentError(None, "need package name")
        if not args.type:
            args.type = self.pipeline()

        self.pkg(CI_PKG) # initialize namespace_id
        if not self.namespace_id:
            raise Exception("missing namespace id")

        if os.path.exists(args.package):
            logger.error("please remove the local file or directory '%s' first", args.package)
            return 1

        r = self._get_response('projects/{}'.format(urllib.parse.quote(os.path.join(self.group, args.package), safe='')))
        if r.ok:
            logger.error("%s/%s already exists", self.group, args.package)
            return 1

        pkg = self._post('projects', data={
            'name': args.package,
            'namespace_id': self.namespace_id,
            'ci_config_path': args.type,
            'default_branch': args.branch,
            'builds_access_level': 'enabled',
            })
        if pkg is None:
            return 1

        b = args.branch
        if args.branch.endswith("/main"):
            b = b[:-4]+'*'

        r = self._post('projects/{}/protected_branches'.format(pkg['id']), data={'name': b})
        if r is None:
            return 2

        repo_url = pkg['ssh_url_to_repo']
        repo = git.Repo.clone_from(repo_url, args.package)
        author = repo.index.commit("Initialize package").author
        repo.remotes.origin.push()

        logger.info("%s/%s with branch %s created".format(self.group, args.package, args.branch))

        if args.type == "gbp":
            self.create_debian_package_template(args, author)         

        return 0
    
    def create_debian_package_template(self, args, author):
        debian_directory = os.path.join(args.package, 'debian')
        debian_source_directory = os.path.join(debian_directory, 'source')
        debian_control = os.path.join(debian_directory, 'control')
        debian_rules = os.path.join(debian_directory, 'rules')
        debian_format = os.path.join(debian_source_directory, 'format')

        os.makedirs(debian_source_directory, exist_ok=True)
        
        with open(debian_rules, "w") as rules_file:
            rules_file.write(textwrap.dedent("""\
                #!/usr/bin/make -f

                %:
                \tdh $@
                """))

        with open(debian_control, "w") as control_file:
            control_file.write(textwrap.dedent("""\
                Source: {package}
                Maintainer: {author_name} <{author_email}>
                Build-Depends:
                    debhelper-compat (= 13)
                Standards-Version: 4.6.2

                Package: {package}
                Architecture: any
                Multi-Arch: foreign
                Depends:
                    ${{shlibs:Depends}},
                    ${{misc:Depends}},
                Description: <add your package description here>
                """).format(
                    package=args.package,
                    author_name=author.name,
                    author_email=author.email
                ))
        with open(debian_format, "w") as format_file:
            format_file.write("3.0 (native)\n")

        logger.info("Created debian package template, please adjust the rules and control file as needed")

    @assert_package
    def do_build(self, args):
        ci_project_dir = '/build'
        if hasattr(args, 'shell'):
            if args.shell is None or args.shell == '':
                args.shell = '/bin/bash'
        else:
            args.shell = None
            # just to make sure nobody hardcodes it :)
            ci_project_dir = '/'+''.join(random.sample(ci_project_dir[1:], k=len(ci_project_dir[1:])))

        try:
            repo = git.Repo('.')
        except git.exc.InvalidGitRepositoryError:
            repo = None
        if repo is None:
            logger.error("invalid repo: %s", args.package)
            return 1

        branch = str(repo.head.reference)

        pkg = self.pkg(args.package)
        env = self._load_variables_remote(pkg)

        tmpdir = self._get_job_artifacts(args.branch, args.package, 'calculate-env')
        if not tmpdir:
            logger.error("failed to load pipeline artifacts for %s: make sure to run the pipeline once", args.package)
            return 1
        try:
            with open(os.path.join(tmpdir.name, 'variables.env'), 'r', encoding='utf-8') as f:
                variables = f.read()
                env |= dict(line.split('=', 1) for line in variables.splitlines() if '=' in line)
        finally:
            tmpdir.cleanup()

        arch_map = {
                'x86_64': 'amd64',
                'aarch64': 'arm64',
                }

        platform = "linux/{}".format(arch_map.get(args.architecture, args.architecture))
        env['ARCHITECTURE'] = arch_map.get(args.architecture, args.architecture)

        env['CI_PROJECT_DIR'] = ci_project_dir
        env['CI_COMMIT_BRANCH'] = branch
        env['CI_COMMIT_REF_NAME'] = branch
        env['CI_COMMIT_REF_SLUG'] = re.sub(r'[^a-z0-9]', '-', branch.lower()).strip('-')[:63]
        env['CI_PROJECT_NAMESPACE'] = self.group

        # expand all variables
        for key, value in env.items():
            env[key] = re.sub(r'\${([A-Z_][A-Z0-9_]*)}', lambda m: env.get(m.group(1), ''), value)

        env_file = tempfile.NamedTemporaryFile(prefix='.gitlab_env.', dir='.', mode='w', delete=False)
        for k in env:
            logger.debug("%s=%s", k, env[k])
            env_file.write('{0}={1}\n'.format(k, env[k]))
        env_file.close()

        cmd = ["docker", "run", '--env-file', env_file.name, "--rm",
                "-v", "{}:{}".format(os.getcwd(), ci_project_dir),
                "--platform", platform, '-w', ci_project_dir]

        image = env['IMAGE']
        script = env['REPO_SETUP_CMD'] + " ; " + env['BUILD_CMD']

        if args.shell:
            print("+++ run to build the package:")
            print(script)
            print("+++")
            cmd += ['-it', image, args.shell]
        else:
            cmd += [image, '/usr/bin/bash', '-c', script]

        logger.info("updating %s", image)
        r = subprocess.run(('docker', 'pull', image), check=False)
        if r.returncode:
            os.unlink(env_file.name)
            return r.returncode

        r = subprocess.run(('ls', '-al', env_file.name), check=False)

        logger.info(cmd)
        r = subprocess.run(cmd, check=False)

        os.unlink(env_file.name)

        return r.returncode

    def do_workspace(self, args):
        if args.action == 'enter':
            workspace_branch = args.workspace_branch

            if hasattr(args, 'package'):
                try:
                    repo = git.Repo('.')
                except git.exc.InvalidGitRepositoryError:
                    repo = None
                if repo is None:
                    logger.error("invalid repo: %s", args.package)
                    return 1

                default_branch = self.pkg(os.path.basename(repo.working_dir))['default_branch']

                if args.workspace_branch not in repo.branches:
                    logger.error("Branch \"%s\" not found in %s. Using default branch \"%s\"", args.workspace_branch, repo.working_dir, default_branch)
                    workspace_branch = default_branch

            os.environ['LICHOS_BRANCH'] = workspace_branch

            subprocess.run([os.environ.get('SHELL', '/bin/sh')])

    @assert_package
    def do_getartifacts(self, args):
        pkg = self.pkg(args.package)
        branch_name = args.branch
        job_name = args.job_name
        artifacts_dir = 'artifacts'

        if not branch_name:
            branch_name = pkg['default_branch']

        if job_name:
            if os.path.exists(artifacts_dir):
                shutil.rmtree(artifacts_dir)

            tempdir = self._get_job_artifacts(branch_name, args.package, job_name)

            if tempdir:
                os.makedirs(artifacts_dir, exist_ok=True)
                for fn in os.listdir(tempdir.name):
                    shutil.move(os.path.join(tempdir.name, fn), os.path.join(artifacts_dir, fn))
                return 0
            else:
                logger.error("Failed to get artifacts for job %s", job_name)
                return 1
        
        pipelines = self._get("projects/{}/pipelines?ref={}&per_page=1&status=success".format(pkg['id'], branch_name), all_pages=False)
        jobs = self._get("projects/{}/pipelines/{}/jobs".format(pkg['id'], pipelines[0]['id']))

        links = []
        for job in jobs:
            if "build" in job['name'] or "create" in job['name']:
                links.append("{}: {}/artifacts/browse".format(job['name'], job['web_url']))
        
        if links:
            print("Artifacts links:")
            for link in links:
                print(link)
        else:
            logger.warning("No artifacts found")

        return 0


    GITLAB_API = "/api/v4/"

    def url(self, path):
        return f'https://{self.host}{self.GITLAB_API}{path}'


def main(args):

    # do some work here
    logger.info("main")

    workspace_branch = os.environ.get('LICHOS_BRANCH', None)
    if workspace_branch:
        args.branch = workspace_branch

    tool = Tool()
    if not tool.configure(args):
        return 1

    f = getattr(tool, 'do_{}'.format(args.command.replace('-', '_')), None)
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
    parser.add_argument("--debug", action="store_true", help="debug output")
    parser.add_argument("--verbose", "-v", action="store_true", help="verbose")
    parser.add_argument("--host", help="gitlab host name")
    parser.add_argument("--project", help="project to work with. Must end in /pkg")
    parser.add_argument("--branch", help="branch name for some commands")
    parser.add_argument("--dump", action="store_true", help="some command allow dumping json data")

    subparsers = parser.add_subparsers(dest="command", title="Commands")

    sp = subparsers.add_parser("list", help="list packages")

    sp = subparsers.add_parser("show", help="show packages")
    sp.add_argument("package", nargs='?', help="some package name")
    sp.add_argument("--branches", action="store_true", help="show branches")

    sp = subparsers.add_parser("status", help="build status of package")
    sp.add_argument("package", nargs='?', help="some package name")

    sp = subparsers.add_parser("log", help="log file of job")
    sp.add_argument("jobname", help="job name")
    sp.add_argument("package", nargs='?', help="package name")
    sp.add_argument("--wait", action="store_true", help="wait for job to start")

    sp = subparsers.add_parser("ctree", help="check repo tree")
    sp.add_argument("--buildlist", action="store_true", help="print build list")

    sp = subparsers.add_parser("enable", help="enable package build")
    sp.add_argument("package", nargs='?', help="some package name")
    sp.add_argument("type", nargs='?', help="build type name")

    sp = subparsers.add_parser("disable", help="disable package build")
    sp.add_argument("package", nargs='?', help="some package name")

    sp = subparsers.add_parser("trigger", help="trigger package build")
    sp.add_argument("package", nargs='?', help="some package name")
    sp.add_argument("--all", action="store_true", help="trigger all packages")

    sp = subparsers.add_parser("clone", help="clone a package")
    sp.add_argument("package", help="package name")

    sp = subparsers.add_parser("create", help="create a package")
    sp.add_argument("package", help="package name")
    sp.add_argument("type", nargs='?', help="build type")

    sp = subparsers.add_parser("pdiff", help="print diff to parent")
    sp.add_argument("package", nargs='?', help="some package name")

    sp = subparsers.add_parser("build", help="build package")
    sp.add_argument("package", nargs='?', help="some package name")
    sp.add_argument("--architecture", nargs='?', default=os.uname().machine, help="architecture to build for")
    sp.add_argument("--script", help="force different script")
    sp.add_argument("--shell", nargs='?', default=argparse.SUPPRESS,  help="launch shell instead of executing build command")

    sp = subparsers.add_parser("browse", help="open browser")
    sp.add_argument("package", nargs='?', help="some package name")

    sp = subparsers.add_parser("workspace", help="set workspace branch")
    sp.add_argument("action", help="action to perform - enter | exit")
    sp.add_argument("workspace_branch", nargs='?', help="branch name")
    
    sp = subparsers.add_parser("getartifacts", help="download pipeline artifacts")
    sp.add_argument("package", nargs='?', help="some package name")
    sp.add_argument("job_name", nargs='?', help="pipeline job name")

#    sp = subparsers.add_parser("cat", help="cat stuff")
#    sp.add_argument("file", nargs='*', help="some file name")

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
