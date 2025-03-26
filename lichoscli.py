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

CI_PKG = '00ci'
CI_DEFAULT_PIPELINE_NAME = "gbp"
CI_TEMPLATE = '{name}.yml@{group}/{pkg}'

import argparse
import logging
import os
import re
import sys
import yaml
import requests
import urllib3
import urllib.parse
import json
import subprocess
import configparser
import random
from datetime import datetime
from git import Repo
from tabulate import tabulate
from time import sleep
from collections import namedtuple

from pprint import pprint

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

class Tool(object):
    citemplate = CI_TEMPLATE
    ci_pkg = CI_PKG

    # name -> json struct
    _packages = {}
    token = None
    namespace_id = None

    def configure(self, host, group) -> bool:
        self.host = host
        self.group = group
        self.package = None

        glabcfgfn = None
        glabcfg = None
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
                                self.host= r.group('host')
                                logger.debug("found host %s in %s", self.host, fn)
                            if not self.group:
                                self.group =r.group('group')
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

        if not self.group:
            logger.error("please specify project")
            return False

        if not self.host:
            logger.error("please specify host")
            return False

        self.token = glabcfg['hosts'][self.host].get('token')
        if not self.token:
            logger.error("missing token in %s", glabcfgfn)
            return False

        return True

    def _get_response(self, path):
        response = requests.get(
            self.url(path),
            headers={"Authorization": f"Bearer {self.token}"},
            allow_redirects=False
        )
        return response

    def _get(self, path, all_pages=True):
        response = requests.get(
            self.url(path),
            headers={"Authorization": f"Bearer {self.token}"},
            allow_redirects=False
        )
        if response.status_code != 200:
            logger.error("failed GET %s", path)
            return None

        j = response.json()

        if all_pages:
            l = getattr(response, 'links', None)
            while l and 'next' in l:
                url = l['next']['url']
                response = requests.get(
                    url,
                    headers={"Authorization": f"Bearer {self.token}", },
                    allow_redirects=False
                )
                if response.status_code != 200:
                    logger.warning("failed GET %s", url)
                    break

                if (isinstance(j, dict)):
                    j |= response.json()
                elif (isinstance(j, list)):
                    j += response.json()
                else:
                    logger.warning("unknown type %s", type(j))

                l = getattr(response, 'links', None)

        return j

    def _put(self, path, data):
        response = requests.put(
            self.url(path),
            headers={"Authorization": f"Bearer {self.token}"},
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
            headers={"Authorization": f"Bearer {self.token}"},
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
            headers={"Authorization": f"Bearer {self.token}"},
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

    def packages(self) -> dict:
        if not self._packages:
            r = self._get_response('groups/{}/projects'.format(urllib.parse.quote(self.group, safe='')))
            if r.status_code == 404 and '/' not in self.group:
                r = self._get_response('users/{}/projects'.format(urllib.parse.quote(self.group, safe='')))

            j = r.json()
            if j is not None:
                for p in j:
                    if self.namespace_id is None and 'namespace' in p:
                        self.namespace_id = p['namespace']['id']
                    self._packages[p['path']] = p
            logger.debug("{} namespace id {}".format(self.group, self.namespace_id))

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

            r = self._get('projects/{}/variables'.format(pkg['id']))
            if r:
                t = [['type', 'key', 'value', 'hidden', 'protected', 'masked', 'raw', 'scope', 'description']]
                for v in r:
                    t.append([v[k] if k != 'value' or v['masked'] == False else '***' for k in ('variable_type', 'key', 'value', 'hidden', 'protected', 'masked', 'raw', 'environment_scope', 'description')])
                print("\nVariables:")
                print(tabulate(t, headers='firstrow'))

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

    def do_status(self, args):
        if not args.package and self.package:
            args.package = self.package
        if args.package and args.package != self.ci_pkg:
            return self._status_package(args)
        return self._status_all(args)

    def _status_package(self, args):
        pkg = self.pkg(args.package)
        r = self._get('projects/{}/pipelines?ref={}&per_page=1'.format(pkg['id'], args.branch if args.branch else pkg['default_branch']), all_pages=False)
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
        r = self._get('projects/{}/pipelines/{}/jobs'.format(pkg['id'], r['id']))
        if not r:
            return 1

        print()
        t = [['Id', 'Name', 'Stage', 'Status']]
        for job in r:
            t.append([job[k] for k in ('id', 'name', 'stage', 'status')])
        print(tabulate(t, headers='firstrow'))

    def _status_all(self, args):
        t = [['Name', 'Type', 'Enabled', 'Status' ]]
        for pn in sorted(self.packages().keys()):
            p = self.pkg(pn)
            status = None
            ci = self.pretty_format_enabled(p['ci_config_path'])
            on = self.pretty_format_enabled(p['builds_access_level'])
            r = self._get('projects/{}/pipelines?ref={}&per_page=1'.format(p['id'], args.branch if args.branch else p['default_branch']), all_pages=False)
            if r is not None and len(r):
                status = r[0]['status']
            r = [p['path'], ci, on, status]
            if 'forked_from_project' in p:
                logger.warning("%s forked from %s", pn, p['forked_from_project']['path_with_namespace'])
            t.append(r)
        print(tabulate(t, headers='firstrow'))

    @assert_package
    def do_enable(self, args):
        pkg = self.pkg(args.package)
        if args.type and re.match(r'^[a-z][a-z0-9]+$', args.type) is None:
            logger.error("Pipeline name must be all lowercase letters and digits")
            return False
        cipath = self.pipeline(args.type, args.branch)
        r = self._put('projects/{}'.format(pkg['id']), data={'builds_access_level': 'enabled', 'ci_config_path': cipath})
        return True

    @assert_package
    def do_disable(self, args):
        pkg = self.pkg(args.package)
        r = self._put('projects/{}'.format(pkg['id']), data={'builds_access_level': 'disabled'})

    @assert_package
    def do_trigger(self, args):
        pkg = self.pkg(args.package)
        r = self._post('projects/{}/pipeline?ref={}'.format(pkg['id'], args.branch if args.branch else pkg['default_branch']))
        if r is None:
            return 1
        if args.dump:
            print(json.dumps(r, indent=2))
        else:
            t = [['Setting', 'Value']]
            for i in ('sha', 'ref', 'status', 'web_url'):
                t.append([i, r[i]])
            print(tabulate(t, headers='firstrow'))

        return True

    @assert_package
    def do_clone(self, args):
        pkg = self.pkg(args.package)
        repo_url = pkg['ssh_url_to_repo']
        repo = Repo.clone_from(repo_url, args.package)
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
                u = y.get('Repository', None)
                if u:
                    logger.debug("Adding upstream %s", u)
                    upstream = repo.create_remote("upstream", u)
                    upstream.fetch()

        return True

    def _pdiff_local(self, args):
        repo = Repo('.')
        assert not repo.bare
        if repo is None:
            logger.error("failed to init git repo")
        if not 'parent' in repo.remotes:
            logger.error('Missing parent repo')
            return False
        parent = repo.remotes.parent
        refname = repo.head.reference

        if not str(refname) in repo.remotes.parent.refs:
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

        r = subprocess.run(('xdg-open', pkg['web_url']))
        return r.returncode

    def _load_variables_remote(self, pkg):
        variables = {}

        kind = pkg['namespace']['kind']
        if kind == 'group':
            r = self._get('groups/{}/variables'.format(pkg['namespace']['id']))
            if r:
                t = [['type', 'key', 'value', 'hidden', 'protected', 'masked', 'raw', 'scope', 'description']]
                for v in r:
                    if logger.isEnabledFor(logging.DEBUG):
                        t.append([v[k] if k != 'value' or v['masked'] == False else '***' for k in ('variable_type', 'key', 'value', 'hidden', 'protected', 'masked', 'raw', 'environment_scope', 'description')])
                    variables[v['key']] = v['value']
                if logger.isEnabledFor(logging.DEBUG):
                    print("\nGroup Variables:")
                    print(tabulate(t, headers='firstrow'))
        else:
            logger.error("Don't know how to handle '{}' variables".format(kind))


        r = self._get('projects/{}/variables'.format(pkg['id']))
        if r:
            t = [['type', 'key', 'value', 'hidden', 'protected', 'masked', 'raw', 'scope', 'description']]
            for v in r:
                if logger.isEnabledFor(logging.DEBUG):
                    t.append([v[k] if k != 'value' or v['masked'] == False else '***' for k in ('variable_type', 'key', 'value', 'hidden', 'protected', 'masked', 'raw', 'environment_scope', 'description')])
                variables[v['key']] = v['value']
            if logger.isEnabledFor(logging.DEBUG):
                print(tabulate(t, headers='firstrow'))
                print("\nVariables:")

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
        repo = Repo.clone_from(repo_url, args.package)
        repo.index.commit("Initialize package")
        repo.remotes.origin.push()

        logger.info("%s/%s with branch %s created".format(self.group, args.package, args.branch))

        return 0

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

        repo = Repo('.')
        if repo is None:
            logger.error("invalid repo")
            return 1

        branch = str(repo.head.reference)

        pkg = self.pkg(args.package)


        if args.pipeline:
            data = open(args.pipeline, 'r')
        else:
            ci = pkg['ci_config_path']
            if ci == '':
                 ci = self.pipeline()

            if ci == '.gitlab-ci.yml':
                p = 'projects/{}/repository/files/{}/raw'.format(pkg['id'], ci)
            else:
                parsed = parse_ci_config_path(ci)
                if parsed is None:
                    logger.error("Invalid pipeline definition")
                    return False
                if parsed.group != self.group:
                    logger.error("Cant fetch pipeline from different group (%s) yet", parsed.group)
                    return False
                p = 'projects/{}/repository/files/{}.yml/raw'.format(self.pkg(parsed.pkg)['id'], parsed.name)
                if parsed.branch:
                    p += "?ref="+parsed.branch

            r = self._get_response(p)
            if r.status_code != 200:
                logger.error("failed to fetch pipeline definition")
                return False
            data = r.text

        ci = yaml.safe_load(data)
        ci.setdefault('default', {})

        if not args.target:
            targets = []
            for t in ci.keys():
                if 'extends' not in ci[t]:
                    continue
                if '.build-package' in ci[t]['extends']:
                    targets.append(t)
            logger.error("missing target. Valid targets: %s", ', '.join(targets))
            return -1

        image = None
        if 'image' in ci['.build-package']:
            image = ci['.build-package']['image']
        elif 'image' in ci[args.target]:
            image = ci[args.target]['image']
        elif 'image' in ci['default']:
            image = ci['default']['image']
        elif 'image' in ci:
            logger.warning("image at top level gitlab-ci.yml is deprecated:\n"
                    + "https://docs.gitlab.com/ci/yaml/#globally-defined-image-services-cache-before_script-after_script")
            image = ci['image']

        if image is None:
            raise Exception("no image configured")

        env = self._load_variables_remote(pkg)

        if 'variables' in ci:
            env |= ci['variables']
        if 'variables' in ci['.build-package']:
            env |= ci['.build-package']['variables']
        if 'variables' in ci[args.target]:
            env |= ci[args.target]['variables']

        env['CI_PROJECT_DIR'] = ci_project_dir
        env['CI_COMMIT_BRANCH'] = branch
        env['CI_COMMIT_REF_NAME'] = branch
        env['CI_COMMIT_REF_SLUG'] = re.sub(r'[^a-z0-9]', '-', branch.lower()).strip('-')[:63]
        env['CI_PROJECT_NAMESPACE'] = self.group

        def _expandvar(m):
            k = m.group(1)
            return env[k] if k in env else ''

        image = re.sub(r'\${([A-Z]+)}', _expandvar, image)

        if 'DOCKER-AARCH64' in ci[args.target]['tags']:
            platform = "linux/arm64"
        elif 'DOCKER' in ci[args.target]['tags']:
            platform = "linux/amd64"
        else:
            logger.error("unknown target platform")
            return 1

        script = []
        if args.script:
            script = [ args.script ]
        else:
            if 'before_script' in ci:
                logger.warning("before_script at top level gitlab-ci.yml is deprecated:\n"
                        + "https://docs.gitlab.com/ci/yaml/#globally-defined-image-services-cache-before_script-after_script")
                script += ci['before_script']
            for s in ('before_script', 'script'):
                if s in ci['.build-package']:
                    script += ci['.build-package'][s]
                elif s in ci['default']:
                    script += ci['default'][s]

        env_file = "_gitlab_env"
        with open(env_file, 'w') as fh:
            for k in env.keys():
                fh.write('{0}={1}\n'.format(k, env[k]))

        fn = "_gitlab_script"
        with open(fn, 'w') as fh:
            fh.write("#!/bin/bash -xe\n")
            fh.write('mount\nls -al /\n')
            fh.write('\n'.join(['\n.'.join(x) if isinstance(x, list) else x for x in script]) + '\n')
        os.chmod(fn, 0o755)

        cmd = ["docker", "run", '--env-file', env_file, "--rm", "-v", "{}:{}".format(os.getcwd(), ci_project_dir),
                "--platform", platform, '-w', ci_project_dir]

        if args.shell:
            print("+++ run {} to build the package".format(os.path.join(ci_project_dir, fn)))
            cmd += ['-it', image, args.shell]
        else:
            cmd += [image, os.path.join(ci_project_dir, fn)]

        logger.info("updating %s", image)
        r = subprocess.run(('docker', 'pull', image))
        r.check_returncode()

        logger.info(cmd)
        r = subprocess.run(cmd)

        return r.returncode


    def url(self, path):
        return 'https://{}//api/v4/{}'.format(self.host, path)


def main(args):

    # do some work here
    logger.info("main")

    tool = Tool()
    if not tool.configure(args.host, args.project):
        return 1

    f = getattr(tool, 'do_{}'.format(args.command.replace('-', '_')), None)
    if f is None:
        logger.error("%s() not implemented", args.command)
        return 1

    r = f(args)
    if r is None:
        return 0
    if isinstance(r, bool):
        return r == False
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

    sp = subparsers.add_parser("enable", help="enable package build")
    sp.add_argument("package", nargs='?', help="some package name")
    sp.add_argument("type", nargs='?', help="build type name")

    sp = subparsers.add_parser("disable", help="disable package build")
    sp.add_argument("package", nargs='?', help="some package name")

    sp = subparsers.add_parser("trigger", help="trigger package build")
    sp.add_argument("package", nargs='?', help="some package name")

    sp = subparsers.add_parser("clone", help="clone a package")
    sp.add_argument("package", help="package name")

    sp = subparsers.add_parser("create", help="create a package")
    sp.add_argument("package", help="package name")
    sp.add_argument("type", nargs='?', help="build type")

    sp = subparsers.add_parser("pdiff", help="print diff to parent")
    sp.add_argument("package", nargs='?', help="some package name")

    sp = subparsers.add_parser("build", help="build package")
    sp.add_argument("package", nargs='?', help="some package name")
    sp.add_argument("target", nargs='?', help="target")
    sp.add_argument("--pipeline", help="force different pipeline (local)")
    sp.add_argument("--script", help="force different script")
    sp.add_argument("--shell", nargs='?', default=argparse.SUPPRESS,  help="launch shell instead of executing build command")

    sp = subparsers.add_parser("browse", help="open browser")
    sp.add_argument("package", nargs='?', help="some package name")

#    sp = subparsers.add_parser("cat", help="cat stuff")
#    sp.add_argument("file", nargs='*', help="some file name")

    args = parser.parse_args()

    if not getattr(args, 'command', None):
        parser.print_help()
        sys.exit(1)

    if args.debug:
        level = logging.DEBUG
    elif args.verbose:
        level = logging.INFO
    else:
        level = None

    logging.basicConfig(level=level, format='[%(levelname).1s] %(message)s')

    sys.exit(main(args))

# vim: sw=4 et
