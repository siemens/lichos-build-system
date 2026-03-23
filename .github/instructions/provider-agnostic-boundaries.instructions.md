---
description: "Use when creating or modifying lichoscli command modules or core services. Enforces provider-agnostic boundaries, core abstractions, and separation from provider-specific implementations."
name: "Provider-Agnostic Boundaries"
applyTo: "lichoscli/commands/*.py, lichoscli/core/services/**/*.py"
---
# Provider-Agnostic Boundaries

- Treat provider agnosticism as a hard rule in `lichoscli/commands` and `lichoscli/core/services`: do not import from `lichoscli/providers` or provider SDKs such as `gitlab` or `github`.
- Commands should handle argument parsing, prompting, and presentation only. Put business logic in `lichoscli/core/services`.
- Core services should depend on generic abstractions declared in `lichoscli/core`, not on provider-specific classes or data shapes.
- If new provider-specific behavior is needed, add or extend a provider-agnostic interface in `lichoscli/core` and keep the concrete implementation hidden in `lichoscli/providers`.
- Resolve shared services through `di_container.obtain_ref(...)` rather than constructing provider implementations directly in command code.
- Avoid provider-shaped data access in commands and core services, including raw `.attributes` dictionaries, provider-only fields, or direct manager APIs. Expose required data through core models, interfaces, or service methods instead.
- Preserve existing command conventions: command class names end with `Command`, command files stay focused on orchestration, and command code should use the UI abstraction (`self.output`, `self.prompts`, `self.console`).