import requests, logging, aiohttp, asyncio, os, time

from io import BytesIO
from requests.exceptions import RequestException

from core.config import config


DEFAULT_HEADERS = {
    'User-Agent': 'ano_valor/0.0.0',
}

BUST_API_URL = "https://visage.surgeplay.com/bust/"

async def request(url: str, headers: dict = None, return_type: str = "json", use_wynn_auth: bool = False):
    all_headers = {**DEFAULT_HEADERS, **(headers or {})}

    if use_wynn_auth:
        all_headers['Authorization'] = f"Bearer {config.WYNN_API_KEY}"

    try:
        res = requests.get(url, headers=all_headers)
        res.raise_for_status()

        if return_type == "json":
            try:
                data = res.json()

                if (
                    isinstance(data, dict)
                    and "/v3/player/" in url
                    and data.get("code") == 300
                    and data.get("error") == "MultipleObjectsReturned"
                ):
                    objects = data.get("objects") or {}
                    if isinstance(objects, dict) and objects:
                        prefuuid = None

                        for probscorrectuuid, candidate_obj in objects.items():
                            if not isinstance(candidate_obj, dict):
                                continue
                            if candidate_obj.get("supportRank") is not None:
                                prefuuid = probscorrectuuid
                                break

                        if prefuuid is None:
                            prefuuid = next(iter(objects.keys()), None)

                        if isinstance(prefuuid, str) and "-" not in prefuuid and len(prefuuid) == 32:
                            prefuuid = (
                                prefuuid[:8]
                                + '-'
                                + prefuuid[8:12]
                                + '-'
                                + prefuuid[12:16]
                                + '-'
                                + prefuuid[16:20]
                                + '-'
                                + prefuuid[20:]
                            )

                        if prefuuid:
                            query = ""
                            if "?" in url:
                                query = url[url.index("?"):]

                            retry_url = f"https://api.wynncraft.com/v3/player/{prefuuid}{query}"
                            if retry_url != url:
                                logging.info(f"PLAYER STATS multiple objects for {url}; retrying by uuid {prefuuid}")
                                return await request(
                                    retry_url,
                                    headers=headers,
                                    return_type=return_type,
                                    use_wynn_auth=use_wynn_auth,
                                )

                return data
            except ValueError:
                logging.warning(f"Failed to parse JSON from {url}")
        elif return_type == "image":
            return res.content
        elif return_type == "stream":
            return BytesIO(res.content)
        else:
            logging.warning(f"Unsupported return_type: {return_type}")

    except RequestException as e:
        logging.warning(f"Request error while accessing {url}: {e}")
    except Exception as e:
        logging.warning(f"Unexpected error while accessing {url}: {e}")

    # Return None if any error occurs
    return None



async def request_with_csrf(csrf_url: str, url: str, return_type: str = "json"):
    session = requests.Session()

    try:
        csrf_res = session.get(csrf_url, headers=DEFAULT_HEADERS)
        csrf_res.raise_for_status()

        csrf_token = session.cookies.get("csrf_token")
        if not csrf_token:
            logging.warning(f"CSRF token not found in cookies from {url}")

        headers = {
            **DEFAULT_HEADERS,
            "X-CSRF-Token": csrf_token,
            "Content-Type": "application/json"
        }

        res = session.get(url, headers=headers)
        res.raise_for_status()

        if return_type == "json":
            try:
                return res.json()
            except ValueError:
                logging.warning(f"Failed to parse JSON from {url}")
        elif return_type == "image":
            return res.content
        elif return_type == "stream":
            return BytesIO(res.content)
        else:
            logging.warning(f"Unsupported return_type: {return_type}")

    except RequestException as e:
        logging.warning(f"Request error while accessing {url}: {e}")
    except Exception as e:
        logging.warning(f"Unexpected error: {e}")

    return None



async def download_player_bust(session: aiohttp.ClientSession, name: str, filename: str, retry: bool = True):
    from util.uuid import get_uuid_from_name

    try:
        uuid = await get_uuid_from_name(name)
    except Exception as e:
        logging.error(f"Failed to resolve UUID for {name}: {e}")
        return None

    try:
        url = f"{BUST_API_URL}{uuid if uuid else name}.png"

        async with session.get(url, headers=DEFAULT_HEADERS, timeout=2) as response:
            if response.status == 200:
                content = await response.read()
                with open(filename, "wb") as f:
                    f.write(content)
                return True
            elif response.status == 404:
                return False
            else:
                if retry:
                    return await download_player_bust(session, name, filename, retry=False)
                else:
                    logging.warning(f"Failed to fetch {name} ({uuid}): HTTP {response.status}")
    except Exception as e:
        logging.error(f"Error fetching {name} ({uuid}): {type(e).__name__}: {e}")

    return None



async def fetch_player_busts(names: list[str]):
    tasks = []
    now = time.time()

    async with aiohttp.ClientSession() as session:
        for name in names:
            filename = f"/tmp/{name}_model.png"

            if os.path.exists(filename) and now - os.path.getmtime(filename) < 24 * 3600:
                continue

            tasks.append(download_player_bust(session, name, filename))

        await asyncio.gather(*tasks)
