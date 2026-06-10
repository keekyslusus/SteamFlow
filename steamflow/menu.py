from .localization import Localizer


STORE_ACTION_RESULT_SOURCES = frozenset({"store", "specials", "top_sellers", "store_collection"})
STORE_CART_RESULT_SOURCES = STORE_ACTION_RESULT_SOURCES | frozenset({"wishlist"})


def _tr(translator, key, default=None, **values):
    if callable(translator):
        try:
            return translator(key, **values)
        except TypeError:
            return translator(key, **values)
    return Localizer("en").tr(key, **values)


def get_refund_menu_copy(refund_state, name, tr=None):
    if refund_state == "likely":
        return (
            _tr(tr, "menu.refund.likely.title"),
            _tr(
                tr,
                "menu.refund.likely.subtitle",
                name=name,
            ),
        )
    if refund_state == "unclear":
        return (
            _tr(tr, "menu.refund.unclear.title"),
            _tr(
                tr,
                "menu.refund.unclear.subtitle",
                name=name,
            ),
        )
    return "", ""


def is_store_action_result_source(result_source):
    return str(result_source or "") in STORE_ACTION_RESULT_SOURCES


def is_store_cart_result_source(result_source):
    return str(result_source or "") in STORE_CART_RESULT_SOURCES


def get_steam_client_context_menu_entries(
    default_icon,
    settings_icon,
    community_icon,
    wishlist_icon=None,
    top_sellers_icon=None,
    deals_icon=None,
    tr=None,
):
    return [
        {
            "title": _tr(tr, "menu.steam.main.title"),
            "subtitle": _tr(tr, "menu.steam.main.subtitle"),
            "icon": default_icon,
            "method": "open_steam",
        },
        {
            "title": _tr(tr, "menu.steam.settings.title"),
            "subtitle": _tr(tr, "menu.steam.settings.subtitle"),
            "icon": settings_icon,
            "method": "open_steam_settings",
        },
        {
            "title": _tr(tr, "menu.steam.friends.title"),
            "subtitle": _tr(tr, "menu.steam.friends.subtitle"),
            "icon": community_icon,
            "method": "open_steam_friends",
        },
        {
            "title": _tr(tr, "menu.steam.wishlist.title"),
            "subtitle": _tr(tr, "menu.steam.wishlist.subtitle"),
            "icon": wishlist_icon or default_icon,
            "method": "open_my_steam_wishlist",
        },
        {
            "title": _tr(tr, "menu.steam.top_sellers.title"),
            "subtitle": _tr(tr, "menu.steam.top_sellers.subtitle"),
            "icon": top_sellers_icon or default_icon,
            "method": "open_steam_top_sellers",
        },
        {
            "title": _tr(tr, "menu.steam.specials.title"),
            "subtitle": _tr(tr, "menu.steam.specials.subtitle"),
            "icon": deals_icon or default_icon,
            "method": "open_steam_specials",
        },
    ]


def get_game_context_menu_entries(
    app_id,
    name,
    install_path,
    is_owned,
    refund_state,
    default_icon,
    steamdb_icon,
    buy_icon,
    csrin_icon,
    guides_icon,
    discussions_icon,
    screenshot_icon,
    refund_icon,
    properties_icon,
    location_icon,
    download_icon,
    trash_icon,
    wishlist_add_icon=None,
    wishlist_remove_icon=None,
    is_unreleased=False,
    can_add_to_cart=False,
    can_add_to_wishlist=False,
    can_remove_from_wishlist=False,
    show_steamdb=True,
    show_csrin=True,
    steamid64=None,
    tr=None,
):
    entries = []
    if app_id:
        entries.append(
            {
                "title": _tr(tr, "menu.store.open_steam.title"),
                "subtitle": _tr(
                    tr,
                    "menu.store.open_steam.subtitle",
                    name=name,
                    app_id=app_id,
                ),
                "icon": default_icon,
                "method": "open_steam_store_page",
                "parameters": [app_id],
            }
        )
        if show_steamdb:
            entries.append(
                {
                    "title": _tr(tr, "menu.store.open_steamdb.title"),
                    "subtitle": _tr(tr, "menu.store.open_steamdb.subtitle", name=name),
                    "icon": steamdb_icon,
                    "method": "open_steamdb_page",
                    "parameters": [app_id],
                }
            )
        if can_add_to_cart:
            entries.append(
                {
                    "title": _tr(tr, "menu.store.add_cart.title"),
                    "subtitle": _tr(tr, "menu.store.add_cart.subtitle", name=name),
                    "icon": buy_icon,
                    "method": "add_to_steam_cart",
                    "parameters": [app_id, steamid64] if steamid64 else [app_id],
                }
            )
        if can_add_to_wishlist:
            entries.append(
                {
                    "title": _tr(tr, "menu.store.add_wishlist.title"),
                    "subtitle": _tr(tr, "menu.store.add_wishlist.subtitle", name=name),
                    "icon": wishlist_add_icon or default_icon,
                    "method": "add_to_steam_wishlist",
                    "parameters": [app_id, steamid64] if steamid64 else [app_id],
                }
            )
        if can_remove_from_wishlist:
            entries.append(
                {
                    "title": _tr(tr, "menu.store.remove_wishlist.title"),
                    "subtitle": _tr(tr, "menu.store.remove_wishlist.subtitle", name=name),
                    "icon": wishlist_remove_icon or trash_icon,
                    "method": "remove_from_steam_wishlist",
                    "parameters": [app_id, steamid64] if steamid64 else [app_id],
                }
            )
        if install_path and show_csrin:
            entries.append(
                {
                    "title": _tr(tr, "menu.community.search_csrin.title"),
                    "subtitle": _tr(tr, "menu.community.search_csrin.subtitle", name=name),
                    "icon": csrin_icon,
                    "method": "search_csrin_page",
                    "parameters": [name],
                }
            )
        if not is_unreleased:
            entries.append(
                {
                    "title": _tr(tr, "menu.community.guides.title"),
                    "subtitle": _tr(tr, "menu.community.guides.subtitle", name=name),
                    "icon": guides_icon,
                    "method": "open_steam_guides_page",
                    "parameters": [app_id],
                }
            )
        entries.append(
            {
                "title": _tr(tr, "menu.community.discussions.title"),
                "subtitle": _tr(tr, "menu.community.discussions.subtitle", name=name),
                "icon": discussions_icon,
                "method": "open_steam_discussions_page",
                "parameters": [app_id],
            }
        )
    if app_id and (install_path or is_owned):
        entries.append(
            {
                "title": _tr(tr, "menu.library.screenshots.title"),
                "subtitle": _tr(tr, "menu.library.screenshots.subtitle", name=name),
                "icon": screenshot_icon,
                "method": "open_steam_screenshots_page",
                "parameters": [app_id],
            }
        )
    if app_id and is_owned and not install_path:
        entries.append(
            {
                "title": _tr(tr, "menu.library.install.title"),
                "subtitle": _tr(tr, "menu.library.install.subtitle", name=name),
                "icon": download_icon,
                "method": "install_steam_game",
                "parameters": [app_id],
            }
        )

    refund_title, refund_subtitle = get_refund_menu_copy(refund_state, name, tr=tr)
    if app_id and install_path and refund_title:
        entries.append(
            {
                "title": refund_title,
                "subtitle": refund_subtitle,
                "icon": refund_icon,
                "method": "open_steam_refund_page",
                "parameters": [app_id],
            }
        )

    if install_path:
        if app_id:
            entries.append(
                {
                    "title": _tr(tr, "menu.library.properties.title"),
                    "subtitle": _tr(tr, "menu.library.properties.subtitle", name=name),
                    "icon": properties_icon,
                    "method": "open_steam_game_properties_page",
                    "parameters": [app_id],
                }
            )
        entries.append(
            {
                "title": _tr(tr, "menu.files.browse.title"),
                "subtitle": _tr(tr, "menu.files.browse.subtitle", name=name),
                "icon": location_icon,
                "method": "open_local_files",
                "parameters": [install_path],
            }
        )
        if app_id:
            entries.append(
                {
                    "title": _tr(tr, "menu.files.uninstall.title"),
                    "subtitle": _tr(tr, "menu.files.uninstall.subtitle", name=name),
                    "icon": trash_icon,
                    "method": "uninstall_steam_game",
                    "parameters": [app_id],
                }
            )

    return entries
