---
description: "Use when implementing or modifying any code that calls the python-gitlab (python3-gitlab) library. Enforces consulting the official python-gitlab v4.9.0 docs before writing API calls, and using idiomatic patterns such as .save(), .get(), and manager methods."
name: "python-gitlab API Usage"
applyTo: "lichoscli/providers/gitlab/**/*.py"
---
# python-gitlab API Usage

- Before implementing any python-gitlab API call, fetch and consult the relevant section of https://python-gitlab.readthedocs.io/en/v4.9.0/index.html to confirm the correct pattern.
- Prefer the idiomatic python-gitlab approach: use `.get()` to fetch a single object, mutate attributes directly, then call `.save()` — do not delete-and-recreate objects when an update is possible.
- Use manager methods (`.list()`, `.get()`, `.create()`, `.delete()`) on the appropriate manager attribute (`project.protectedbranches`, `project.branches`, etc.) as shown in the docs.
- Do not reconstruct payloads from existing object attributes to pass back into `.create()` when `.save()` is available on the object.
- Check the docs for which managers support `SaveMixin` (`.save()`) vs those that are create/delete-only before choosing an update strategy.
