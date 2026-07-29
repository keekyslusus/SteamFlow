import hashlib
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen


DOWNLOAD_TIMEOUT_SECONDS = 20
MAX_PAYLOAD_FILE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class SmokeAPIPayloadFile:
    filename: str
    url: str
    sha256: str
    max_bytes: int = MAX_PAYLOAD_FILE_BYTES


PAYLOAD_FILES = (
    SmokeAPIPayloadFile(
        filename="steam_api.dll",
        url=(
            "https://raw.githubusercontent.com/keekyslusus/"
            "SteamFlow/smapi/smokeapi/steam_api.dll"
        ),
        sha256="145AADFFFDE5140991995D76DCA8F2423E9D7F9DBB66BC21565CEE59746F027B",
    ),
    SmokeAPIPayloadFile(
        filename="steam_api64.dll",
        url=(
            "https://raw.githubusercontent.com/keekyslusus/"
            "SteamFlow/smapi/smokeapi/steam_api64.dll"
        ),
        sha256="3891CD70B8E06CAD474B9EA5B6D7C3D19B9948C41DF2495E3CF02D2A256498EF",
    ),
)


@dataclass(frozen=True)
class SmokeAPIPayloadStatus:
    missing_files: tuple
    invalid_files: tuple

    @property
    def ready(self):
        return not self.missing_files and not self.invalid_files


@dataclass(frozen=True)
class SmokeAPIPayloadDownloadResult:
    downloaded_files: tuple = ()
    errors: tuple = ()

    @property
    def success(self):
        return not self.errors


def _hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def inspect_smokeapi_payload(payload_dir, payload_files=PAYLOAD_FILES):
    payload_root = Path(payload_dir)
    missing_files = []
    invalid_files = []
    for payload_file in payload_files:
        path = payload_root / payload_file.filename
        if not path.is_file():
            missing_files.append(payload_file.filename)
            continue
        try:
            if _hash_file(path) != payload_file.sha256.upper():
                invalid_files.append(payload_file.filename)
        except OSError:
            invalid_files.append(payload_file.filename)
    return SmokeAPIPayloadStatus(
        missing_files=tuple(missing_files),
        invalid_files=tuple(invalid_files),
    )


def _download_payload_file(payload_file, destination, open_url, timeout_seconds):
    digest = hashlib.sha256()
    total_bytes = 0
    with open_url(payload_file.url, timeout=timeout_seconds) as response:
        with Path(destination).open("xb") as output:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > payload_file.max_bytes:
                    raise ValueError("payload_too_large")
                digest.update(chunk)
                output.write(chunk)

    if total_bytes <= 0:
        raise ValueError("payload_empty")
    if digest.hexdigest().upper() != payload_file.sha256.upper():
        raise ValueError("payload_hash_mismatch")


def download_smokeapi_payload(
    payload_dir,
    payload_files=PAYLOAD_FILES,
    open_url=urlopen,
    timeout_seconds=DOWNLOAD_TIMEOUT_SECONDS,
):
    payload_files = tuple(payload_files)
    payload_root = Path(payload_dir)
    status = inspect_smokeapi_payload(payload_root, payload_files)
    if status.ready:
        return SmokeAPIPayloadDownloadResult()

    required_names = set(status.missing_files) | set(status.invalid_files)
    required_files = tuple(
        payload_file
        for payload_file in payload_files
        if payload_file.filename in required_names
    )

    try:
        payload_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".download-", dir=payload_root) as temp_dir:
            temp_root = Path(temp_dir)
            for payload_file in required_files:
                _download_payload_file(
                    payload_file,
                    temp_root / payload_file.filename,
                    open_url,
                    timeout_seconds,
                )
            for payload_file in required_files:
                (temp_root / payload_file.filename).replace(
                    payload_root / payload_file.filename
                )
    except Exception as error:
        return SmokeAPIPayloadDownloadResult(
            errors=(f"{type(error).__name__}:{error}",),
        )

    final_status = inspect_smokeapi_payload(payload_root, payload_files)
    if not final_status.ready:
        unavailable = final_status.missing_files + final_status.invalid_files
        return SmokeAPIPayloadDownloadResult(
            errors=tuple(f"payload_unavailable:{name}" for name in unavailable),
        )
    return SmokeAPIPayloadDownloadResult(
        downloaded_files=tuple(
            payload_file.filename for payload_file in required_files
        ),
    )
