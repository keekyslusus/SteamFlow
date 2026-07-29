from .friends_service import friend_presence_group, is_favorite_friend, sort_friends
from .localization import Localizer
from .profile_service import PROFILE_STATUS_LABEL_KEYS
from .util_steam_date import format_last_seen


def _tr(translator, key, **values):
    if callable(translator):
        return translator(key, **values)
    return Localizer("en").tr(key, **values)


def get_friend_status_text(friend, tr=None):
    game = str(friend.get("gameextrainfo", "") or "").strip()
    if game:
        return _tr(tr, "profile.status.playing", game=game)
    try:
        state = int(friend.get("personastate", 0) or 0)
    except (TypeError, ValueError):
        state = 0
    return _tr(tr, PROFILE_STATUS_LABEL_KEYS.get(state, "profile.status.offline"))


def get_friend_icon(friend, friends_icon, online_icon, away_icon, offline_icon):
    avatar = str(friend.get("avatarmedium") or friend.get("avatar") or "").strip()
    if avatar:
        return avatar
    group = friend_presence_group(friend)
    if group in {"playing", "online"}:
        return online_icon
    if group == "away":
        return away_icon
    return offline_icon or friends_icon


def _friends_count_form(count):
    count = max(0, int(count or 0))
    if count % 10 == 1 and count % 100 != 11:
        return "one"
    if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        return "few"
    return "many"


def build_friends_playing_suffix(friend_names, tr=None):
    names = [str(name or "").strip() for name in friend_names or []]
    names = [name for name in names if name]
    if not names:
        return ""
    if len(names) == 1:
        text = _tr(tr, "ui.friend_playing", name=names[0])
    else:
        text = _tr(
            tr,
            f"ui.friends_playing.{_friends_count_form(len(names))}",
            count=len(names),
        )
    return f" | {text}"


def build_friend_result(friend, score, result_provider, icons, tr=None, is_favorite=False):
    steamid64 = friend["steamid64"]
    name = friend.get("personaname") or steamid64
    subtitle = get_friend_status_text(friend, tr=tr)
    if friend_presence_group(friend) == "offline":
        last_seen = format_last_seen(friend.get("lastlogoff", 0), tr=tr)
        if last_seen:
            subtitle += f" | {_tr(tr, 'friends.last_seen', when=last_seen)}"
    if is_favorite:
        subtitle = f"★ {subtitle}"
    return result_provider.build_result(
        title=name,
        subtitle=subtitle,
        icon_path=get_friend_icon(
            friend,
            icons["friends"],
            icons["online"],
            icons["away"],
            icons["offline"],
        ),
        action=result_provider.build_action("open_steam_friend_chat", steamid64),
        context_data={
            "menu": "friend",
            "steamid64": steamid64,
            "name": name,
            "gameid": friend.get("gameid", ""),
            "game_name": friend.get("gameextrainfo", ""),
        },
        Score=score,
    )


def build_loading_result(search_term, result_provider, friends_icon, tr=None):
    query = result_provider.build_plugin_query("friends", search_term)
    return result_provider.build_result(
        title=_tr(tr, "friends.loading.title"),
        subtitle=_tr(tr, "friends.loading.subtitle"),
        icon_path=friends_icon,
        action=result_provider.build_change_query_action(query),
        Score=20500,
    )


def build_error_result(error, result_provider, friends_icon, tr=None):
    subtitle_key = "friends.private" if error == "private" else "friends.request_failed"
    action = result_provider.build_action("refresh_steam_friends")
    action["dontHideAfterAction"] = True
    return result_provider.build_result(
        title=_tr(tr, "friends.unavailable"),
        subtitle=_tr(tr, subtitle_key),
        icon_path=friends_icon,
        action=action,
        Score=20500,
    )


def build_unavailable_result(reason, reasons, result_provider, friends_icon, tr=None):
    api_query = result_provider.build_plugin_query("api")
    subtitles = {
        reasons.api_not_configured: _tr(tr, "friends.unavailable_api", api_query=api_query),
        reasons.api_bound_to_another_account: _tr(tr, "friends.unavailable_bound"),
        reasons.no_active_account: _tr(tr, "friends.unavailable_no_account"),
    }
    action = None
    if reason in {reasons.api_not_configured, reasons.api_bound_to_another_account}:
        action = result_provider.build_change_query_action(api_query)
    return result_provider.build_result(
        title=_tr(tr, "friends.unavailable"),
        subtitle=subtitles.get(reason, _tr(tr, "friends.request_failed")),
        icon_path=friends_icon,
        action=action,
        Score=20500,
    )


def build_friends_results(
    items,
    error,
    search_term,
    reasons,
    result_provider,
    icons,
    max_results,
    tr=None,
    favorite_accountids=None,
):
    if error in {
        reasons.api_not_configured,
        reasons.api_bound_to_another_account,
        reasons.no_active_account,
    }:
        return [
            build_unavailable_result(
                error,
                reasons,
                result_provider,
                icons["friends"],
                tr=tr,
            )
        ]
    if error == "loading":
        return [
            build_loading_result(
                search_term,
                result_provider,
                icons["friends"],
                tr=tr,
            )
        ]
    if error:
        return [build_error_result(error, result_provider, icons["friends"], tr=tr)]

    favorite_accountids = set(favorite_accountids or ())
    matches = sort_friends(items, search_term, favorite_accountids)
    if not matches:
        title_key = "friends.empty_search" if search_term else "friends.empty"
        return [
            result_provider.build_result(
                title=_tr(tr, title_key, search_term=search_term),
                subtitle=_tr(tr, "friends.empty.subtitle"),
                icon_path=icons["friends"],
                Score=20500,
            )
        ]
    return [
        build_friend_result(
            friend,
            20500 - index,
            result_provider,
            icons,
            tr=tr,
            is_favorite=is_favorite_friend(friend, favorite_accountids),
        )
        for index, friend in enumerate(matches[:max_results])
    ]
