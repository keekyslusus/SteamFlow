# Steam ClientComm

## Goal

Figure out whether Steam download pause/resume for local games can be controlled programmatically, similar to Steam Mobile remote downloads.

Result: yes, it works through `IClientCommService`, but not with a normal Steam Web API key.

## Final Conclusion

Working path:

- Use `IClientCommService/SetClientAppUpdateState/v1/`
- Authenticate with a Steam `access_token` from the logged-in Steam web/client session
- Send `origin=https://store.steampowered.com`
- `action=1` resumes download
- `action=0` pauses download

This is real and was verified against a live local Steam client.

## Important Finding

A normal user Steam Web API key from `steamcommunity.com/dev/apikey` is not enough for `IClientCommService`.

Observed behavior:

- Regular APIs like `IPlayerService/GetOwnedGames` worked with a normal key
- `IClientCommService/GetAllClientLogonInfo` returned `Unauthorized`
- `IClientCommService/SetClientAppUpdateState` returned `Unauthorized`

So the old `key=...` auth model is not sufficient here.

## What Actually Works

`IClientCommService` accepts authenticated requests with an `access_token`.

Successful authenticated flow:

1. `GetAllClientLogonInfo`
2. `SetClientAppUpdateState`
3. `GetClientAppList`

All of these worked with:

- `access_token=<steam session token>`
- `origin=https://store.steampowered.com`

## Endpoints

### 1. Get desktop sessions

`GET https://api.steampowered.com/IClientCommService/GetAllClientLogonInfo/v1/`

Parameters:

- `access_token`
- `origin`

Successful response example:

```json
{
  "response": {
    "sessions": [
      {
        "client_instanceid": "304697237993669830",
        "protocol_version": 65581,
        "os_name": "Windows 11",
        "machine_name": "DESKTOP-MFAFSKO",
        "os_type": 20,
        "device_type": 1,
        "realm": 1
      }
    ],
    "refetch_interval_sec": 300
  }
}
```

This confirms that the token is authorized for `IClientCommService`.

### 2. Pause / resume a specific app download

`POST https://api.steampowered.com/IClientCommService/SetClientAppUpdateState/v1/`

Parameters:

- `access_token`
- `origin`
- `appid`
- `action`
- optional `client_instanceid`

Action values:

- `1` = resume downloading
- `0` = pause downloading

Successful response:

```json
{
  "response": {}
}
```

### 3. Read current download state

`GET https://api.steampowered.com/IClientCommService/GetClientAppList/v1/`

Useful parameters:

- `access_token`
- `origin`
- `fields=all`
- `include_client_info=true`
- `filter_appids[0]=<appid>`
- optional `client_instanceid`

Successful response example for app `1451940` after resume:

```json
{
  "response": {
    "apps": [
      {
        "appid": 1451940,
        "app": "NEEDY GIRL OVERDOSE",
        "num_downloading": 1,
        "bytes_download_rate": 2148906,
        "bytes_downloaded": "214096304",
        "bytes_to_download": "934525536",
        "changing": true,
        "installed": true,
        "queue_position": 0,
        "estimated_seconds_remaining": 517,
        "update_percentage": 20
      }
    ]
  }
}
```

This is enough for:

- resume/pause UI
- showing percent
- showing speed
- detecting whether the app is actively downloading

## How The Token Was Found

The important clue was that Steam web/client requests in local cache were already calling `api.steampowered.com` with `access_token=...`, not with a normal `key=...`.

### Local cache locations that were useful

- `%LOCALAPPDATA%\\Steam\\htmlcache\\Default\\Cache\\Cache_Data\\data_1`
- `%LOCALAPPDATA%\\Steam\\htmlcache\\Default\\Code Cache\\js\\*`

### What was found in cache

In cache data:

- requests to `IStoreBrowseService/GetItems/v1`
- those requests already contained `access_token=<jwt-like token>`

In JS code cache:

- `GetAllClientLogonInfo`
- `GetClientAppList`
- `SetClientAppUpdateState`
- `EnableOrDisableDownloads`
- `access_token`
- `webapi_token`
- `authwgtoken`
- the string:
  - `Attempting to invoke service ... without auth, but auth is required.`

That strongly suggested:

- `IClientCommService` is meant to be called with session auth
- Steam web/client code already does this internally

## Exact Investigation Path

### Step 1. Verify the endpoint exists

- [steamapi.xpaw.me](https://steamapi.xpaw.me/IClientCommService#SetClientAppUpdateState)

Useful documented methods there:

- `EnableOrDisableDownloads`
- `GetAllClientLogonInfo`
- `GetClientAppList`
- `SetClientAppUpdateState`

Important note:

`xPaw` shows these methods as using `key`, but in practice that was not enough here.

### Step 2. Test with regular Steam Web API key

What worked:

- `IPlayerService/GetOwnedGames`

What did not work:

- `IClientCommService/GetAllClientLogonInfo`
- `IClientCommService/SetClientAppUpdateState`

Observed result:

- `Unauthorized`

Conclusion:

- protected `ClientComm` methods require a different auth layer

### Step 3. Search Steam Mobile / client clues

Found references in Steam mobile/client assets to:

- `CClientComm_SetClientAppUpdateState_Request`
- `CClientComm_EnableOrDisableDownloads_Request`
- `RemoteDownloads`
- `GenerateAccessTokenForApp`
- `webapi_token`
- `loyalty_webapi_token`

This suggested remote download control is real and session-backed.

### Step 4. Search local Steam htmlcache

Found:

- cached `api.steampowered.com` requests with `access_token`
- JS cache entries showing `ClientComm` method names and auth requirement strings

This was the turning point.

### Step 5. Retry `ClientComm` with `access_token`

`GetAllClientLogonInfo` succeeded immediately.

After that:

- `SetClientAppUpdateState(action=1)` succeeded
- `GetClientAppList` confirmed the game started downloading

## Minimal Curl Examples

Replace `<ACCESS_TOKEN>` and `<APPID>`.

### Get sessions

```bash
curl -L --get "https://api.steampowered.com/IClientCommService/GetAllClientLogonInfo/v1/" \
  --data-urlencode "access_token=<ACCESS_TOKEN>" \
  --data-urlencode "origin=https://store.steampowered.com"
```

### Resume download

```bash
curl -L -X POST "https://api.steampowered.com/IClientCommService/SetClientAppUpdateState/v1/" \
  --data-urlencode "access_token=<ACCESS_TOKEN>" \
  --data-urlencode "origin=https://store.steampowered.com" \
  --data-urlencode "appid=<APPID>" \
  --data-urlencode "action=1"
```

### Pause download

```bash
curl -L -X POST "https://api.steampowered.com/IClientCommService/SetClientAppUpdateState/v1/" \
  --data-urlencode "access_token=<ACCESS_TOKEN>" \
  --data-urlencode "origin=https://store.steampowered.com" \
  --data-urlencode "appid=<APPID>" \
  --data-urlencode "action=0"
```

### Read app download state

```bash
curl -L --get "https://api.steampowered.com/IClientCommService/GetClientAppList/v1/" \
  --data-urlencode "access_token=<ACCESS_TOKEN>" \
  --data-urlencode "origin=https://store.steampowered.com" \
  --data-urlencode "fields=all" \
  --data-urlencode "include_client_info=true" \
  --data-urlencode "filter_appids[0]=<APPID>"
```

## Suggested Plugin Implementation

### Auth source

Prefer a local helper that extracts the current Steam `access_token` from local client cache.

Requirements:

- do not log the token
- do not expose it in UI
- treat it like a secret
- tolerate token rotation and fetch a fresh token when needed

### Pause / resume logic

For a local game row:

- if app is updating/installing and active, show `Pause updating game`
- if app is paused, show `Resume updating game`

Action:

- call `SetClientAppUpdateState`

Where possible, also refresh state from:

- `GetClientAppList`

### State detection

Good signals from `GetClientAppList`:

- `changing`
- `num_downloading`
- `bytes_download_rate`
- `update_percentage`
- `estimated_seconds_remaining`
- `queue_position`

This is stronger than relying only on local `StateFlags`.

## Notes About `client_instanceid`

`client_instanceid` appears optional.

Observed behavior:

- Steam accepted requests without explicitly sending it
- `GetAllClientLogonInfo` returned the available session

Recommendation:

- if only one desktop session exists, omission is probably fine
- if multiple sessions exist, select the correct one from `GetAllClientLogonInfo`

## Security Notes

- Do not print tokens in logs and do not store them in plaing config
- Tokens appear to expire/rotate
- A normal Steam Web API key should not be treated as equivalent to this session token

## Practical Summary

For this feature, the real stack is:

- local Steam client session
- locally discoverable `access_token`
- `IClientCommService`
- `SetClientAppUpdateState` for pause/resume
- `GetClientAppList` for UI state

This is the first approach that was both:

- actually functional
- specific to one app
- fast enough for plugin UX
