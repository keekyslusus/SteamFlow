class MixinContractError(RuntimeError):
    pass


def _append_contract_targets(targets, source_name, names):
    for name in names:
        normalized = str(name or "").strip()
        if not normalized:
            continue
        targets.setdefault(normalized, [])
        if source_name not in targets[normalized]:
            targets[normalized].append(source_name)


def collect_declared_mixin_contracts(plugin_cls):
    required_attrs = {}
    required_methods = {}
    for cls in plugin_cls.__mro__:
        if cls is object:
            continue
        source_name = cls.__name__
        _append_contract_targets(required_attrs, source_name, getattr(cls, "REQUIRED_PLUGIN_ATTRS", ()))
        _append_contract_targets(required_methods, source_name, getattr(cls, "REQUIRED_PLUGIN_METHODS", ()))
    return required_attrs, required_methods


def collect_declared_provider_contracts(plugin_cls):
    required_providers = {}
    for cls in plugin_cls.__mro__:
        if cls is object:
            continue
        source_name = cls.__name__
        _append_contract_targets(required_providers, source_name, getattr(cls, "REQUIRED_PLUGIN_PROVIDERS", ()))
    return required_providers


def _format_missing_contracts(title, missing_contracts):
    if not missing_contracts:
        return ""
    formatted_items = []
    for name, sources in sorted(missing_contracts.items()):
        source_label = ", ".join(sorted(sources))
        formatted_items.append(f"{name} (required by {source_label})")
    return f"{title}: " + "; ".join(formatted_items)


def validate_declared_mixin_contracts(plugin):
    required_attrs, required_methods = collect_declared_mixin_contracts(type(plugin))
    required_providers = collect_declared_provider_contracts(type(plugin))

    missing_attrs = {
        name: sources
        for name, sources in required_attrs.items()
        if not hasattr(plugin, name)
    }
    missing_methods = {
        name: sources
        for name, sources in required_methods.items()
        if not callable(getattr(plugin, name, None))
    }
    providers = getattr(plugin, "providers", None)
    missing_providers = {
        name: sources
        for name, sources in required_providers.items()
        if providers is None or not hasattr(providers, name)
    }

    if not missing_attrs and not missing_methods and not missing_providers:
        return

    message_parts = [
        _format_missing_contracts("Missing plugin attrs", missing_attrs),
        _format_missing_contracts("Missing plugin methods", missing_methods),
        _format_missing_contracts("Missing plugin providers", missing_providers),
    ]
    message = " | ".join(part for part in message_parts if part)
    raise MixinContractError(message)
