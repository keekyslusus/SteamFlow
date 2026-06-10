import json
import urllib.parse
import urllib.request


USER_AGENT = "Mozilla/5.0"
DEFAULT_HTTP_HEADERS = {"User-Agent": USER_AGENT}
FORM_CONTENT_TYPE = "application/x-www-form-urlencoded; charset=UTF-8"


def build_headers(headers=None, include_user_agent=True):
    merged_headers = {}
    if include_user_agent:
        merged_headers.update(DEFAULT_HTTP_HEADERS)
    merged_headers.update(headers or {})
    return merged_headers


def decode_json_bytes(raw_data, encoding="utf-8"):
    return json.loads(raw_data.decode(encoding))


def decode_response_json(response, encoding="utf-8"):
    return decode_json_bytes(response.data, encoding=encoding)


def http_get_json(http_get, url, timeout, headers=None):
    response = http_get(
        url,
        timeout=timeout,
        headers=build_headers(headers),
    )
    return decode_response_json(response)


def http_pool_request(http_pool, urllib3_module, method, url, timeout, headers=None):
    response = http_pool.request(
        str(method or "GET").upper(),
        url,
        headers=headers,
        timeout=timeout,
        retries=False,
    )
    if response.status >= 400:
        raise urllib3_module.exceptions.HTTPError(f"HTTP {response.status}")
    return response


def http_pool_get(http_pool, urllib3_module, url, timeout, headers=None):
    return http_pool_request(http_pool, urllib3_module, "GET", url, timeout=timeout, headers=headers)


def urllib_get_json(url, timeout, headers=None, opener=None):
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(url, headers=build_headers(headers))
    with opener(request, timeout=timeout) as response:
        return decode_json_bytes(response.read())


def build_form_headers(origin=None, referer=None, headers=None):
    form_headers = {
        "Content-Type": FORM_CONTENT_TYPE,
    }
    if origin:
        form_headers["Origin"] = origin
    if referer:
        form_headers["Referer"] = referer
    return build_headers({**form_headers, **(headers or {})})


def build_form_body(fields=None):
    return urllib.parse.urlencode(fields or {}, doseq=True).encode("utf-8")


def build_url_with_query(url, fields=None):
    if not fields:
        return url
    encoded_fields = urllib.parse.urlencode(fields, doseq=True)
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{encoded_fields}"


def urllib_json_request(url, method="GET", fields=None, timeout=3, headers=None, origin=None, referer=None, opener=None):
    opener = opener or urllib.request.urlopen
    method = str(method or "GET").upper()
    if method == "GET":
        request = urllib.request.Request(
            build_url_with_query(url, fields),
            headers=build_headers(headers),
        )
    else:
        request = urllib.request.Request(
            url,
            data=build_form_body(fields),
            headers=build_form_headers(origin=origin, referer=referer, headers=headers),
            method=method,
        )

    with opener(request, timeout=timeout) as response:
        return decode_json_bytes(response.read())


def urllib_form_request(url, fields=None, method="POST", timeout=4, headers=None, origin=None, referer=None, opener=None):
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(
        url,
        data=build_form_body(fields),
        headers=build_form_headers(origin=origin, referer=referer, headers=headers),
        method=str(method or "POST").upper(),
    )
    with opener(request, timeout=timeout) as response:
        raw_data = response.read()
        content_type = response.headers.get("Content-Type", "")
    if "json" in content_type:
        return decode_json_bytes(raw_data), raw_data
    try:
        return decode_json_bytes(raw_data), raw_data
    except Exception:
        return {}, raw_data


def download_http_get_to_file(http_get, url, save_path, timeout=2, headers=None):
    response = http_get(url, timeout=timeout, headers=build_headers(headers))
    with open(save_path, "wb") as out_file:
        out_file.write(response.data)
    return True
