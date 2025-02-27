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

CIPKG = '00ci'
CITEMPLATE = 'gbp.yml@{}/'+CIPKG

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
import configparser
from datetime import datetime
from git import Repo
from tabulate import tabulate
from time import sleep

from pprint import pprint

def assert_package(func):
    def wrapper(self, args):
        if not args.package:
            raise argparse.ArgumentError(None, "Missing package parameter")
        return func(self, args)

    return wrapper

class Tool(object):
    citemplate = CITEMPLATE

    # name -> json struct
    _packages = {}
    token = None

    def configure(self, host, group) -> bool:
        self.host = host
        self.group = group

        glabcfg = None
        home = os.path.expanduser('~')
        for p in ('/', '/snap/glab/current'):
            fn = f"{home}/{p}/.config/glab-cli/config.yml"
            if os.path.exists(fn):
                with open(fn, 'r') as fh:
                    glabcfg = yaml.safe_load(fh)

        if glabcfg is None:
            logging.error("Failed to parse gitlab config. Please create one")
            return False

        if not self.host and 'host' in glabcfg:
            self.host = glabcfg['host']
            logging.debug("got host %s from gitlab config", self.host)

        if not self.host or not self.group:
            for p in ('.', CIPKG):
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
                                logging.debug("found host %s in %s", self.host, fn)
                            if not self.group:
                                self.group =r.group('group')
                                logging.debug("found group %s in %s", self.group, fn)
                            if 'package' in args and not args.package:
                                pkg = r.group('package')
                                if pkg.endswith('.git'):
                                    pkg = pkg[:-4]
                                args.package = pkg
                                logging.debug("found package %s in %s", pkg, fn)
                            break

        if not self.host and not self.group:
            logging.error("please specify host and project")
            return False

        if not self.group:
            logging.error("please specify project")
            return False

        if not self.host:
            logging.error("please specify host")
            return False

        self.token = glabcfg['hosts'][self.host]['token']

        return True

    def _get_response(self, path):
        response = requests.get(
            self.url(path),
            headers={"Authorization": f"Bearer {self.token}"},
            allow_redirects=False
        )
        return response

    def _get(self, path):
        response = requests.get(
            self.url(path),
            headers={"Authorization": f"Bearer {self.token}"},
            allow_redirects=False
        )
        if response.status_code != 200:
            logging.error("failed GET %s", path)
            return None

        j = response.json()

        l = getattr(response, 'links', None)
        while l and 'next' in l:
            url = l['next']['url']
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.token}", },
                allow_redirects=False
            )
            if response.status_code != 200:
                logging.warning("failed GET %s", url)
                break

            if (isinstance(j, dict)):
                j |= response.json()
            elif (isinstance(j, list)):
                j += response.json()
            else:
                logging.warning("unknown type %s", type(j))

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
            logging.error("failed PUT %s", path)
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
            logging.error("failed POST %s: %s", path, response.status_code)
            return None

        return response.json()

    def do_cat(self, args):
        print("cat")
        for f in args.file:
            pprint(f)

    def packages(self) -> dict:
        if not self._packages:
            r = self._get_response('groups/{}'.format(urllib.parse.quote(self.group, safe='')))
            if r.status_code == 404 and '/' not in self.group:
                r = self._get_response('users/{}/projects'.format(urllib.parse.quote(self.group, safe='')))
                j = r.json()
                if j is not None:
                    for p in j:
                        self._packages[p['path']] = p
            else:
                j = r.json()
                if j is not None:
                    for p in j['projects']:
                        self._packages[p['path']] = p
        return self._packages

    def do_list(self, args):
        t = [['Name', 'Build', 'Branch']]
        for pn in sorted(self.packages().keys()):
            p = self.packages()[pn]
            status = None
            ci = p['ci_config_path']
            if ci == self.citemplate.format(self.group):
                ci = 'enabled'
            elif ci == '.gitlab-ci.yml':
                ci = 'local'
            r = [p['path'], ci, p['default_branch']]
            if 'forked_from_project' in p:
                logging.warning("%s forked from %s", pn, p['forked_from_project']['path_with_namespace'])
            t.append(r)
        print(tabulate(t, headers='firstrow'))

    @assert_package
    def do_show(self, args):
        pkg = self.packages()[args.package]
        r = self._get('projects/{}'.format(pkg['id']))
        if r is None:
            return 1

        if args.dump:
            print(json.dumps(r, indent=2))
        elif args.branches:
            r = self._get('projects/{}/repository/branches'.format(pkg['id']))
            if r:
                t = [['SHA', 'Age', 'Name']]
                for b, c, d in [(b['name'], b['commit']['short_id'], b['commit']['committed_date']) for b in r]:
                    n = b
                    if b == pkg['default_branch']:
                        n = "\033[32m{}\033[m".format(b)
                    p = datetime.fromisoformat(d)
                    t.append([c, "{}".format((datetime.now(p.tzinfo) - p).days), n])
                print(tabulate(t, headers='firstrow'))
        else:
            t = [['Setting', 'Value']]
            for i in ('id', 'path', 'ci_config_path', 'default_branch', 'forked'):
                if i == 'forked':
                    if 'forked_from_project' in pkg:
                        t.append([i, pkg['forked_from_project']['path_with_namespace']])
                else:
                    t.append([i, pkg[i]])
            print(tabulate(t, headers='firstrow'))

            r = self._get('projects/{}/variables'.format(pkg['id']))
            if r:
                t = [['type', 'key', 'value', 'hidden', 'protected', 'masked', 'raw', 'scope', 'description']]
                for v in r:
                    t.append([v[k] for k in ('variable_type', 'key', 'value', 'hidden', 'protected', 'masked', 'raw', 'environment_scope', 'description')])
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
        pkg = self.packages()[args.package]
        r = self._get('projects/{}/pipelines/latest'.format(pkg['id']))
        if r is None:
            return 1

        job = self._find_job_by_name(pkg['id'], r['id'], args.jobname)
        if job is None:
            logging.error("jobs with name %s not found", args.log)
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
                logging.error("failed to get log file for job %s", job['id'])
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
        if args.package and args.package != CIPKG:
            return self._status_package(args)
        return self._status_all(args)

    def _status_package(self, args):
        pkg = self.packages()[args.package]
        r = self._get('projects/{}/pipelines/latest'.format(pkg['id']))
        if r is None:
            return 1
        if args.dump:
            print(json.dumps(r, indent=2))
        else:
            t = [['Setting', 'Value']]
            for i in ('sha', 'ref', 'status', 'web_url'):
                t.append([i, r[i]])
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
        t = [['Name', 'Build', 'Status' ]]
        for pn in sorted(self.packages().keys()):
            p = self.packages()[pn]
            status = None
            ci = p['ci_config_path']
            if ci == self.citemplate.format(self.group):
                ci = 'enabled'
            elif ci == '.gitlab-ci.yml':
                ci = 'local'
            r = self._get('projects/{}/pipelines/latest'.format(p['id']))
            if r is not None:
                status = r['status']
            r = [p['path'], ci, status]
            if 'forked_from_project' in p:
                logging.warning("%s forked from %s", pn, p['forked_from_project']['path_with_namespace'])
            t.append(r)
        print(tabulate(t, headers='firstrow'))

    @assert_package
    def do_enable(self, args):
        pkg = self.packages()[args.package]
        if not args.template:
            args.template = self.citemplate.format(self.group)
        r = self._put('projects/{}'.format(pkg['id']), data={'ci_config_path': args.template})

    @assert_package
    def do_disable(self, args):
        pkg = self.packages()[args.package]
        r = self._put('projects/{}'.format(pkg['id']), data={'ci_config_path': ''})

    @assert_package
    def do_trigger(self, args):
        pkg = self.packages()[args.package]
        r = self._post('projects/{}/pipeline?ref={}'.format(pkg['id'], pkg['default_branch']))
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

    def do_clone(self, args):
        repo_url = "git@{}:{}/{}.git".format(self.host, self.group, args.package)
        repo = Repo.clone_from(repo_url, args.package)

        return True

    def url(self, path):
        return 'https://{}//api/v4/{}'.format(self.host, path)


def main(args):

    # do some work here
    logger = logging.getLogger("Tool")
    logger.info("main")

    tool = Tool()
    if not tool.configure(args.host, args.project):
        return 1

    f = getattr(tool, 'do_{}'.format(args.func), None)
    if f is None:
        logger.error("%s() not implemented", args.func)
    else:
        f(args)

    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
                    description="tool to manage package builds in gitlab")
    parser.add_argument("--dry", action="store_true", help="dry run")
    parser.add_argument("--debug", action="store_true", help="debug output")
    parser.add_argument("--verbose", "-v", action="store_true", help="verbose")
    parser.add_argument("--host", help="gitlab host name")
    parser.add_argument("--project", help="project to work with. Must end in /pkg")
    parser.add_argument("--dump", action="store_true", help="some command allow dumping json data")

    subparsers = parser.add_subparsers(title="Commands")

    parser_list_packages = subparsers.add_parser("list", help="list packages")
    parser_list_packages.set_defaults(func='list')

    parser_show_packages = subparsers.add_parser("show", help="show packages")
    parser_show_packages.set_defaults(func='show')
    parser_show_packages.add_argument("package", nargs='?', help="some package name")
    parser_show_packages.add_argument("--branches", action="store_true", help="show branches")

    parser_status_packages = subparsers.add_parser("status", help="build status of package")
    parser_status_packages.set_defaults(func='status')
    parser_status_packages.add_argument("package", nargs='?', help="some package name")

    parser_log_packages = subparsers.add_parser("log", help="log file of job")
    parser_log_packages.set_defaults(func='log')
    parser_log_packages.add_argument("jobname", help="job name")
    parser_log_packages.add_argument("package", nargs='?', help="package name")
    parser_log_packages.add_argument("--wait", action="store_true", help="wait for job to start")

    parser_enable_packages = subparsers.add_parser("enable", help="enable package build")
    parser_enable_packages.set_defaults(func='enable')
    parser_enable_packages.add_argument("package", nargs='?', help="some package name")
    parser_enable_packages.add_argument("template", nargs='?', help="template name")

    parser_disable_packages = subparsers.add_parser("disable", help="disable package build")
    parser_disable_packages.set_defaults(func='disable')
    parser_disable_packages.add_argument("package", nargs='?', help="some package name")

    parser_trigger_packages = subparsers.add_parser("trigger", help="trigger package build")
    parser_trigger_packages.set_defaults(func='trigger')
    parser_trigger_packages.add_argument("package", nargs='?', help="some package name")

    parser_clone_packages = subparsers.add_parser("clone", help="clone a package")
    parser_clone_packages.set_defaults(func='clone')
    parser_clone_packages.add_argument("package", help="package name")

#    parser_cat = subparsers.add_parser("cat", help="cat stuff")
#    parser_cat.add_argument("file", nargs='*', help="some file name")
#    parser_cat.set_defaults(func=tool.do_cat)

    args = parser.parse_args()

    if not getattr(args, 'func', None):
        parser.print_help()
        sys.exit(1)

    if args.debug:
        level = logging.DEBUG
    elif args.verbose:
        level = logging.INFO
    else:
        level = None

    logging.basicConfig(level=level)

    sys.exit(main(args))

# vim: sw=4 et
