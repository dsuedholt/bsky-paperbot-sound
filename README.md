# bsky-paperbot-sound

pings arxiv rss feeds and posts them on bluesky. powering https://bsky.app/profile/arxiv-sound.bsky.social

forked from [bsky-paperbot](https://github.com/apoorvalal/bsky_paperbot), with some modifications:
- simply post all papers with announce-type 'new' once per day, no logging / archive required
- use `atproto` library to access bluesky api
- add an embed card with title and author information
- use the free Gemini API to summarize the abstract to fit the bluesky character limit

## make your own bsky bot 

+ fork this repository (or the original [bsky-paperbot](https://github.com/apoorvalal/bsky_paperbot))
+ create a bluesky account 
+ get a bluesky password / username, and set them in `Settings > Secrets and Variables > BSKYBOT, BSKYPWD`
+ use different RSS feeds, or do something else
