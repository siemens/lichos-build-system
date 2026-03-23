---
description: "Use when creating or modifying Python files in lichoscli. Enforces avoiding f-strings, preferring .format(...) for general interpolation and logger argument placeholders for logging calls."
name: "Python String Formatting"
applyTo: "**/*.py"
---
# Python String Formatting

- Treat avoiding f-strings as a hard rule in Python files. Prefer plain strings or `.format(...)` for general interpolation.
- Do not introduce f-strings in logging calls. Keep deferred interpolation by passing arguments to the logger instead.
- When formatting values into strings, default to `.format(...)` unless a plain literal or existing helper already keeps the code simpler.
- If an existing block already uses f-strings heavily, do not mix styles within the same small expression flow; either preserve the local pattern or refactor the block consistently.