def get_refund_menu_copy(refund_state, name):
    if refund_state == "likely":
        return (
            "Support: Open Refund Page",
            f"Likely eligible: under 2h played. Steam also checks purchase date for {name}.",
        )
    if refund_state == "unclear":
        return (
            "Support: Check Refund Options",
            f"Eligibility unclear. Open Steam support page for {name}.",
        )
    return "", ""


def get_steam_client_context_menu_entries(default_icon, settings_icon, community_icon):
    return [
        {
            "title": "Steam: Open Main Window",
            "subtitle": "Open the Steam client",
            "icon": default_icon,
            "method": "open_steam",
        },
        {
            "title": "Steam: Open Settings",
            "subtitle": "Open Steam settings",
            "icon": settings_icon,
            "method": "open_steam_settings",
        },
        {
            "title": "Steam: Open Friends",
            "subtitle": "Open Steam friends and chat",
            "icon": community_icon,
            "method": "open_steam_friends",
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
    guides_icon,
    discussions_icon,
    screenshot_icon,
    refund_icon,
    properties_icon,
    location_icon,
    download_icon,
    trash_icon,
    is_unreleased=False,
):
    entries = []
    if app_id:
        entries.append(
            {
                "title": "Store: Open in Steam",
                "subtitle": f"Open store page for {name} (ID:{app_id})",
                "icon": default_icon,
                "method": "open_steam_store_page",
                "parameters": [app_id],
            }
        )
        entries.append(
            {
                "title": "Store: Open in SteamDB",
                "subtitle": f"Open SteamDB page for {name}",
                "icon": steamdb_icon,
                "method": "open_steamdb_page",
                "parameters": [app_id],
            }
        )
        if not is_unreleased:
            entries.append(
                {
                    "title": "Community: Open Guides",
                    "subtitle": f"Open Steam guides for {name}",
                    "icon": guides_icon,
                    "method": "open_steam_guides_page",
                    "parameters": [app_id],
                }
            )
        entries.append(
            {
                "title": "Community: Open Discussions",
                "subtitle": f"Open Steam discussions for {name}",
                "icon": discussions_icon,
                "method": "open_steam_discussions_page",
                "parameters": [app_id],
            }
        )
    if app_id and (install_path or is_owned):
        entries.append(
            {
                "title": "Library: Open Recordings & Screenshots",
                "subtitle": f"Open recordings and screenshots for {name}",
                "icon": screenshot_icon,
                "method": "open_steam_screenshots_page",
                "parameters": [app_id],
            }
        )
    if app_id and is_owned and not install_path:
        entries.append(
            {
                "title": "Library: Install Game",
                "subtitle": f"Open Steam install prompt for {name}",
                "icon": download_icon,
                "method": "install_steam_game",
                "parameters": [app_id],
            }
        )

    refund_title, refund_subtitle = get_refund_menu_copy(refund_state, name)
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
                    "title": "Library: Open Properties",
                    "subtitle": f"Open Steam properties for {name}",
                    "icon": properties_icon,
                    "method": "open_steam_game_properties_page",
                    "parameters": [app_id],
                }
            )
        entries.append(
            {
                "title": "Files: Browse Local Files",
                "subtitle": f"Open installation folder for {name}",
                "icon": location_icon,
                "method": "open_local_files",
                "parameters": [install_path],
            }
        )
        if app_id:
            entries.append(
                {
                    "title": "Files: Uninstall Game",
                    "subtitle": f"Open Steam uninstall prompt for {name}",
                    "icon": trash_icon,
                    "method": "uninstall_steam_game",
                    "parameters": [app_id],
                }
            )

    return entries
