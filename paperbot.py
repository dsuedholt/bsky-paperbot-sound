"""
Script to post new articles from a daily arxiv paper feed. Bring your own handle and app-password.
"""

import os
import time
from datetime import datetime

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

    for attempt in range(10):
        try:
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
        except Exception as e:
            print(f"Attempt {attempt + 1}/10 failed: {e}")
            if attempt == 9:
                print("All 10 attempts failed, exiting")
                exit(1)
            print("Waiting 5 minutes before retry...")
            time.sleep(300)


def shorten_abstracts(entries: list[ArxivEntry]) -> None:
    genai.configure(api_key=os.environ["GEMINI_KEY"])

    model = genai.GenerativeModel(
        "gemini-2.0-flash",
        generation_config=google.generativeai.GenerationConfig(temperature=1.0),
    )

    prompt = \
"""Your job is to summarize the abstract of academic papers for an online newsfeed. The character limit for this newsfeed is 300, but it would be better to err on the side of terseness. The title of the paper will be posted alongside your summary, so avoid repeating or paraphrasing it directly; focus on the information that the abstract adds to the title. Respond with exactly one summary per line, do not use bulletpoints or markdown formatting. Include methods and results. Employ a curt and abrupt writing style that avoids boilerplate.

You will be given the titles and abstracts marked with XML. As an example, this could look like this:
<title>
Study of Lightweight Transformer Architectures for Single-Channel Speech Enhancement
</title>
<abstract>
In speech enhancement, achieving state-of-the-art (SotA) performance while adhering to the computational constraints on edge devices remains a formidable challenge. Networks integrating stacked temporal and spectral modelling effectively leverage improved architectures such as transformers; however, they inevitably incur substantial computational complexity and model expansion. Through systematic ablation analysis on transformer-based temporal and spectral modelling, we demonstrate that the architecture employing streamlined Frequency-Time-Frequency (FTF) stacked transformers efficiently learns global dependencies within causal context, while avoiding considerable computational demands. Utilising discriminators in training further improves learning efficacy and enhancement without introducing additional complexity during inference. The proposed lightweight, causal, transformer-based architecture with adversarial training (LCT-GAN) yields SoTA performance on instrumental metrics among contemporary lightweight models, but with far less overhead. Compared to DeepFilterNet2, the LCT-GAN only requires 6% of the parameters, at similar complexity and performance. Against CCFNet+(Lite), LCT-GAN saves 9% in parameters and 10% in multiply-accumulate operations yet yielding improved performance. Further, the LCT-GAN even outperforms more complex, common baseline models on widely used test datasets.
</abstract>
<title>
Training Articulatory Inversion Models for Inter-Speaker Consistency
</title>
<abstract>
Acoustic-to-Articulatory Inversion (AAI) attempts to model the inverse mapping from speech to articulation. Exact articulatory prediction from speech alone may be impossible, as speakers can choose different forms of articulation seemingly without reference to their vocal tract structure. However, once a speaker has selected an articulatory form, their productions vary minimally. Recent works in AAI have proposed adapting Self-Supervised Learning (SSL) models to single-speaker datasets, claiming that these single-speaker models provide a universal articulatory template. In this paper, we investigate whether SSL-adapted models trained on single and multi-speaker data produce articulatory targets which are consistent across speaker identities for English and Russian. We do this through the use of a novel evaluation method which extracts articulatory targets using minimal pair sets. We also present a training method which can improve interspeaker consistency using only speech data. 
</abstract>

A good response might look like this:

LCT-GAN, a lightweight transformer-based architecture, achieves state-of-the-art performance in single-channel speech enhancement with reduced computational cost; outperforms DeepFilterNet2 with only 6% of its parameters.

Self-Supervised Learning models trained on single and multi-speaker data were evaluated for inter-speaker consistency in articulatory targets using a novel minimal pair set method; a new training method improved consistency.

This concludes the example. Now generate summaries for the following papers:

"""


    abstracts = "\n".join([f"<title>\n{entry.title}\n</title>\n<abstract>\n{entry.abstract}\n</abstract>\n" for entry in entries])

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

    print("Calling Gemini to get shortened abstracts")
    shorten_abstracts(entries)

    # post entries over the course of ~5 hours
    interval = 5 * 60 * 60 / len(entries)

    print(f"Posting one entry every {interval / 60:.1f} minutes")

    bsky_client = Client()

    for entry in entries:
        print(datetime.now().strftime("%H:%M"), f"Posting {entry.link}")

        # login every time to avoid session timeout
        bsky_client.login(os.environ["BSKYBOT"], os.environ["BSKYPWD"])

        for attempt in range(5):
            try:
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
                break
            except Exception as e:
                print(f"Post attempt {attempt + 1}/5 failed: {e}")
                if attempt == 4:
                    print(f"Failed to post {entry.link} after 5 attempts, skipping")
                    break
                print("Waiting 1 minute before retry...")
                time.sleep(60)
        
        time.sleep(interval)


if __name__ == "__main__":
    main()
