import requests


def verify_url(url: str) -> bool:
    """
    Verify if a URL is valid.
    """
    try:
        if url is None or url == "":
            return False
        response = requests.head(url, allow_redirects=True, timeout=5)
        if response.status_code == 200:
            return True
        elif response.status_code == 404:
            print(f"The link {url} is not valid (404 Not Found).")
            return False
        else:
            print(
                f"The link {url} returned an unexpected status code: {response.status_code}"
            )
            return False
    except requests.RequestException as e:
        print(f"An error occurred while checking {url}: {e}")
        return False
