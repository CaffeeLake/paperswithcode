import aiohttp
import asyncio


async def verify_url(url: str) -> bool:
    """
    Verify if a URL is valid using async HTTP requests.
    """
    try:
        if url is None or url == "":
            return False

        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.head(url, allow_redirects=True) as response:
                if response.status == 200:
                    return True
                elif response.status == 404:
                    print(f"The link {url} is not valid (404 Not Found).")
                    return False
                else:
                    print(
                        f"The link {url} returned an unexpected status code: {response.status}"
                    )
                    return False
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(f"An error occurred while checking {url}: {e}")
        return False


if __name__ == "__main__":
    result = asyncio.run(verify_url("https://langgpt.ai"))
    print(result)
