# Repository Guidelines

- Keep `Main.cs` as a thin Flow Launcher entry point: it implements the Flow interfaces and delegates to services.
- Assemble the runtime dependency graph only in `CompositionRoot.cs`.
- Prefer composition and constructor injection. Do not introduce implementation inheritance, abstract base classes, class hierarchies or service locators.
- Give each class one cohesive responsibility; keep feature-specific behavior and resource ownership inside that feature's folder (e.g. `Library/`).
- Keep features loosely coupled: replacing or removing one should mainly affect its own code and composition, not unrelated features.
- Centralize shared behavior and policy in focused services (e.g. opening Steam URIs and pages in `Steam/SteamClient.cs`); avoid duplication and abstractions that do not reduce coupling.
- Apply these principles (1. one cohesive responsibility, 2. keep features loosely coupled, 3. centralize shared behavior) proportionately: prefer the simplest design that makes current changes clear; do not add layers or interfaces solely for hypothetical future replacements.
- No XML docs (`/// <summary>`) and no comments that restate the code; comment only non-obvious why.
- Put all user-visible strings in `src/SteamFlow/Languages/*.xaml` and read them with `IPublicAPI.GetTranslation`; do not hardcode them in C#.
- Do not use em dashes (U+2014); use hyphens (-) instead.

## Build

- Target `net9.0-windows` to match Flow Launcher 2.x; check a dependency's target framework before adding it.
- `scripts/deploy-dev.ps1` builds the plugin, restarts Flow Launcher and installs the build into its plugins folder under a dev ID, the `stc` keyword and the name "SteamFlow (dev)", so it runs next to the installed release.
- The root `plugin.json` is the release manifest (original ID, `steam` keyword); the release workflow reads its version.
