# Repository Guidelines

- `SteamPlugin` is the main plugin shell.
- Mixins provide Flow Launcher-facing behavior and public plugin methods.
- `providers.py` is the dependency boundary between feature areas.
- `state.py` owns grouped plugin state.
- Service modules contain reusable business logic.


## Mixin Rules

Treat existing mixins as a legacy shell around the plugin.

Mixins are okay when they:

- expose plugin methods required by Flow Launcher;
- coordinate a feature at a high level;
- adapt providers/state/services into plugin behavior;
- stay thin enough to understand locally.

Avoid adding new large mixins. If a feature needs substantial logic, put that logic in a normal module or small service first, then call it from a thin mixin method.


## Service Module Rules

Prefer plain modules or small service helpers for new business logic.
Keep service modules boring and explicit. Do not introduce a large dependency injection framework or a component graph just to avoid mixins.


## Provider Rules

Keep using providers as the dependency boundary.

Feature code should prefer provider calls over reaching across the whole plugin surface when practical.

Declare provider requirements with `REQUIRED_PLUGIN_PROVIDERS` when a mixin depends on provider access. Declare direct plugin requirements with `REQUIRED_PLUGIN_ATTRS` and `REQUIRED_PLUGIN_METHODS` when the dependency really must remain on the plugin object.


## State Rules

Keep plugin state grouped in dataclasses under `state.py`.

Avoid adding random new mutable attributes directly to the plugin when they belong to an existing state group. If a new state area grows large, add a dedicated state dataclass instead of scattering attributes.


## Localization Rules

Do not hardcode user-visible text in code; put it in `steamflow/locales/` and access it through the localization helpers.


## Target

- mixins stay as plugin-facing adapters;
- providers describe cross-feature dependencies;
- service modules hold most feature logic;
- state remains explicit and grouped;
