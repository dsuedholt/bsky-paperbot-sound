"""
Script to post new articles from a daily arxiv paper feed. Bring your own handle and app-password.
"""

import time
import os

from bs4 import BeautifulSoup
from collections import namedtuple

from atproto import Client, models

import feedparser
from pylatexenc.latex2text import LatexNodes2Text

ArxivEntry = namedtuple(
    "ArxivEntry",
    ["link", "title", "authors", "abstract", "abstract_short"],
    defaults=[""],
)


def get_arxiv_feed(feed_names: list[str]) -> list[ArxivEntry]:
    feed_url = f"https://export.arxiv.org/rss/{'+'.join(feed_names)}"
    print(f"Fetching feed from {feed_url}")

    feed = feedparser.parse(feed_url)

    if feed.bozo:
        raise feed.bozo_exception

    res = [
        ArxivEntry(
            link=entry.link,
            title=entry.title,
            authors=entry.author,
            abstract=BeautifulSoup(entry.description, "html.parser")
            .text.split("Abstract:")[1]
            .strip(),
        )
        for entry in feed.entries
        if entry.arxiv_announce_type == "new"
    ]
    return res


def main():
    feed = get_arxiv_feed(["cs.SD", "eess.AS"])

    if not feed:
        print("No new entries today")
        exit(0)
    else:
        print(f"Found {len(feed)} new entries")

    bsky_client = Client()
    bsky_client.login(os.environ["BSKYBOT"], os.environ["BSKYPWD"])

    l2t = LatexNodes2Text()

    for entry in feed:
        print(f"Posting {entry.link}")

        bsky_client.send_post(
            entry.title,
            embed=models.AppBskyEmbedExternal.Main(
                external=models.AppBskyEmbedExternal.External(
                    uri=entry.link,
                    title=l2t.latex_to_text(entry.title),
                    description=l2t.latex_to_text(entry.authors),
                )
            ),
        )
        time.sleep(1)


if __name__ == "__main__":
    main()
