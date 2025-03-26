# LiChOS build system command line tool

When called from within a git checkout the tool automatically detects the
package to operate on. It's also possible to make the tool operate on project
level when the 00ci package is checked out.

## Setup

`lichoscli` uses the same configuration file as the [GitLab CLI
tool](https://docs.gitlab.com/editor_extensions/gitlab_cli/) to get
the access token for the gitlab instance. That's by default
`~/.config/glab-cli/config.yml` (snaps use
`~/snap/glab/current/.config/glab-cli/config.yml`). A minimal config
needs a host and token setting:
```
host: "code.acme.example"
hosts:
  code.acme.example:
    token: "<your_access_token>"
    user: joe
```

## Check out 00ci to initialize current directory

	$ lichoscli --project your-group/platform-os/pkg clone 00ci

Once `00ci` is checked out, lichoscli can detect project settings
etc from the current directory.

## List packages in current project

	$ lichoscli list
	Name                        Build    Branch
	--------------------------  -------  -------------
	00ci                                 main
	imx-code-signing-tool       enabled  flocken/main
	initramfs                            flocken/main
	keyctl-caam                 enabled  flocken/main
	[...]

## List packages in a different project

	$ lichoscli --project your-group/pocs/isar/pkg list
	Name                   Build    Branch
	---------------------  -------  ---------------
	00ci                            main
	00documentation        local    main
	bendermqtt             enabled  main
	changelog-generator    enabled  main


## Show package pipeline status

	$ lichoscli status
	Name                        Build    Status
	--------------------------  -------  --------
	00ci
	imx-code-signing-tool       enabled  failed
	keyctl-caam                 enabled  success

## Show settings of a specific package

	$ lichoscli --project your-group/pocs/isar/pkg show keyctl-caam
	Setting         Value
	--------------  -------------------------------------
	id              431660
	path            keyctl-caam
	ci_config_path  gbp.yml@your-group/platform-os/pkg/00ci
	default_branch  flocken/main

	Variables:
	type     key    value    hidden    protected    masked    raw    scope    description
	-------  -----  -------  --------  -----------  --------  -----  -------  -------------
	env_var  TEST   BLUB     False     False        False     False  *        foo bar

## Clone package

It is perfectly fine to clone packages using plain git. Using lichoscli for
this purpose is for convenience. For example lichoscli automatically
adds a `parent` remote if the repo is a fork which in turn enables
the `pdiff` command to work. Also if the
[debian/upstream/metadata](https://wiki.debian.org/UpstreamMetadata) file has a
`Repository` setting, that repo will be added as `upstream` remote.

	$ lichoscli clone keyctl-caam

## Trigger pipeline of a package

	$ cd keyctl-caam
	$ lichoscli trigger

## Show status

	$ lichoscli status
	Setting    Value
	---------  ----------------------------------------------------------------------------------
	sha        cd133fa9ea4aa78d946078d5cf50880873c30a63
	ref        flocken/main
	status     success
	web_url    https://gitlab.example.com/your-group/platform-os/pkg/keyctl-caam/-/pipelines/42559448

	       Id  Name                            Stage    Status
	---------  ------------------------------  -------  --------
	248015835  publish-debian-package-to-iron  deploy   success
	248015834  build-flocken-amd64             build    success
	248015833  build-flocken-arm64             build    success

## Show log file

	$ lichoscli log build-flocken-amd64
	[...]

## Wait for the job to start and show live log

	$ lichoscli log --wait build-flocken-amd64
	[...]

## Local package build

Note that this is rather limited at the moment and expects a certain
layout of the pipeline. It's not generic.

       $ lichoscli build . build-flocken-amd64
       [...]

It's also possible to launch a shell in the build container instead
of starting the build directly. The command will print the name of
a script that can be called to start the build manually

       $ lichoscli build . build-flocken-amd64 --shell
       [...]

Note --shell expect an optional parameter to specify the shell. The
default is /bin/bash but if `--shell` is followed by other
parameters you need to specify it as `--shell=` ie pass an empty
parameter. Otherwise the next option is consumed as shell.

## Create a new package

The default branch, protection and pipeline will be set

       $ lichoscli --branch 'foo/main' create bar

See --help for more commands
