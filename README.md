Tool to manage package builds

When called from within a git checkout the tool automatically detects the
package to operate on. It's also possible to make the tool operate on project
level when the 00ci package is checked out.

Check out 00ci to initialize current directory

	$ lichoscli.py --project your-group/platform-os/pkg clone 00ci

List packages in current project

	$ lichoscli.py list
	Name                        Build    Branch
	--------------------------  -------  -------------
	00ci                                 main
	imx-code-signing-tool       enabled  flocken/main
	initramfs                            flocken/main
	keyctl-caam                 enabled  flocken/main
	[...]

List packages in a different project

	$ lichoscli --project your-group/pocs/isar/pkg list
	Name                   Build    Branch
	---------------------  -------  ---------------
	00ci                            main
	00documentation        local    main
	bendermqtt             enabled  main
	changelog-generator    enabled  main


Show package pipeline status

	$ lichoscli status
	Name                        Build    Status
	--------------------------  -------  --------
	00ci
	imx-code-signing-tool       enabled  failed
	keyctl-caam                 enabled  success

Show settings of a specific package

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

Clone package

	$ lichoscli clone keyctl-caam

Trigger pipeline of a package

	$ cd keyctl-caam
	$ lichoscli trigger

Show status

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

Show log file

	$ lichoscli log build-flocken-amd64
	[...]

Wait for the job to start and show live log

	$ lichoscli log --wait build-flocken-amd64
	[...]

See --help for more commands
