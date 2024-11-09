"""
Script to post new articles from a daily arxiv paper feed. Bring your own handle and app-password.
"""

import os
import time

import google.generativeai
from bs4 import BeautifulSoup
from dataclasses import dataclass

from atproto import Client, models

import google.generativeai as genai

import feedparser
from pylatexenc.latex2text import LatexNodes2Text


@dataclass
class ArxivEntry:
    link: str
    title: str
    authors: str
    abstract: str


BLUESKY_CHAR_LIMIT = 300


def get_arxiv_feed(feed_names: list[str]) -> list[ArxivEntry]:
    feed_url = f"https://export.arxiv.org/rss/{'+'.join(feed_names)}"
    print(f"Fetching feed from {feed_url}")

    feed = feedparser.parse(feed_url)

    if feed.bozo:
        raise feed.bozo_exception

    l2t = LatexNodes2Text()

    return [
        ArxivEntry(
            link=entry.link,
            title=l2t.latex_to_text(entry.title),
            authors=l2t.latex_to_text(entry.author),
            abstract=l2t.latex_to_text(
                BeautifulSoup(entry.description, "html.parser")
                .text.split("Abstract:")[1]
                .strip()
            ),
        )
        for entry in feed.entries
        if entry.arxiv_announce_type == "new"
    ]


def shorten_abstracts(entries: list[ArxivEntry]) -> None:
    genai.configure(api_key=os.environ["GEMINI_KEY"])

    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        generation_config=google.generativeai.GenerationConfig(temperature=0.0),
    )

    prompt = (
        "Below are the titles of various academic papers, followed by their abstracts. Summarize them. Focus your "
        "summary on the information that is not included in the title. Respond with exactly one summary per "
        "line. Include methods and results. Employ a curt and abrupt writing style that avoids boilerplate.\n\n"
    )

    abstracts = "\n".join([f"{entry.title}\n{entry.abstract}\n" for entry in entries])

    chat = model.start_chat()
    response = chat.send_message(prompt + abstracts)

    shortened_abstracts = [line for line in response.text.split("\n") if line]

    too_long = [
        (i, abstract)
        for i, abstract in enumerate(shortened_abstracts)
        if len(abstract) > BLUESKY_CHAR_LIMIT
    ]

    if too_long:
        too_long_idxs, too_long_abstracts = zip(*too_long)

        prompt = "Revise the following summaries:\n\n"
        response = chat.send_message(prompt + "\n\n".join(too_long_abstracts))

        revised_abstracts = [line for line in response.text.split("\n") if line]

        for i, revised_abstract in zip(too_long_idxs, revised_abstracts):
            shortened_abstracts[i] = revised_abstract[:BLUESKY_CHAR_LIMIT]

    for entry, shortened_abstract in zip(entries, shortened_abstracts):
        entry.abstract = shortened_abstract


def main():
    entries = get_arxiv_feed(["cs.SD", "eess.AS"])

    if not entries:
        print("No new entries today")
        exit(0)
    else:
        print(f"Found {len(entries)} new entries")

    bsky_client = Client()
    bsky_client.login(os.environ["BSKYBOT"], os.environ["BSKYPWD"])

    shorten_abstracts(entries)

    for entry in entries:
        print(f"Posting {entry.link}")

        bsky_client.send_post(
            entry.abstract,
            embed=models.AppBskyEmbedExternal.Main(
                external=models.AppBskyEmbedExternal.External(
                    uri=entry.link,
                    title=entry.title,
                    description=entry.authors,
                )
            ),
        )
        time.sleep(1)


if __name__ == "__main__":
    main()
