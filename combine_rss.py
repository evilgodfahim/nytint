#!/usr/bin/env python3
import feedparser
from xml.dom.minidom import Document, parseString
import email.utils
from datetime import datetime, timezone
import os

RSS_URLS = [
    "https://www.nytimes.com/services/xml/rss/nyt/World.xml"
]

ARCHIVE_PREFIX = "https://archive.is/o/N6yE6/"
OUTPUT_FILE = "combined.xml"
MAX_ITEMS = 500
MEDIA_NS = "http://search.yahoo.com/mrss/"

def parse_entry_datetime(entry):
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        from time import mktime
        ts = mktime(entry.published_parsed)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        from time import mktime
        ts = mktime(entry.updated_parsed)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    return datetime.now(tz=timezone.utc)

def get_thumbnail(entry):
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url", "")
    if hasattr(entry, "media_content") and entry.media_content:
        for mc in entry.media_content:
            if mc.get("medium") == "image" or mc.get("type", "").startswith("image/"):
                return mc.get("url", "")
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image/"):
                return enc.get("href", "") or enc.get("url", "")
    return ""

# --- Load existing entries from file ---
existing_entries = []
if os.path.exists(OUTPUT_FILE):
    try:
        with open(OUTPUT_FILE, "rb") as f:
            old_doc = parseString(f.read())
        for item in old_doc.getElementsByTagName("item"):
            def get_text(tag):
                els = item.getElementsByTagName(tag)
                return els[0].firstChild.nodeValue if els and els[0].firstChild else ""
            guid = get_text("guid")
            pub = get_text("pubDate")
            try:
                dt = datetime(*email.utils.parsedate(pub)[:6], tzinfo=timezone.utc)
            except Exception:
                dt = datetime.now(tz=timezone.utc)
            thumbnail = ""
            thumb_nodes = item.getElementsByTagName("media:thumbnail")
            if thumb_nodes:
                thumbnail = thumb_nodes[0].getAttribute("url")
            existing_entries.append({
                "title": get_text("title"),
                "orig_link": guid,
                "archive_link": get_text("link"),
                "summary": get_text("description"),
                "published_dt": dt,
                "thumbnail": thumbnail,
            })
    except Exception as e:
        print(f"⚠️  Could not parse existing file, starting fresh: {e}")

existing_guids = {e["orig_link"] for e in existing_entries}

# --- Fetch new entries ---
new_entries = []
for feed_url in RSS_URLS:
    feed = feedparser.parse(feed_url)
    for entry in feed.entries:
        if entry.link in existing_guids:
            continue
        dt = parse_entry_datetime(entry)
        new_entries.append({
            "title": getattr(entry, "title", "Untitled"),
            "orig_link": entry.link,
            "archive_link": ARCHIVE_PREFIX + entry.link,
            "summary": getattr(entry, "summary", "") or getattr(entry, "description", ""),
            "published_dt": dt,
            "thumbnail": get_thumbnail(entry),
        })

# --- Merge, sort, cap ---
all_entries = new_entries + existing_entries
all_entries.sort(key=lambda x: x["published_dt"], reverse=True)
all_entries = all_entries[:MAX_ITEMS]

# --- Write ---
doc = Document()
rss = doc.createElement("rss")
rss.setAttribute("version", "2.0")
rss.setAttribute("xmlns:media", MEDIA_NS)
doc.appendChild(rss)

channel = doc.createElement("channel")
rss.appendChild(channel)
channel.appendChild(doc.createElement("title")).appendChild(doc.createTextNode("Project Syndicate Archive Feed"))
channel.appendChild(doc.createElement("link")).appendChild(doc.createTextNode("https://www.nytimes.com"))
channel.appendChild(doc.createElement("description")).appendChild(doc.createTextNode("Combined feed with archive links"))

for it in all_entries:
    item_el = doc.createElement("item")
    channel.appendChild(item_el)
    item_el.appendChild(doc.createElement("title")).appendChild(doc.createTextNode(it["title"]))
    item_el.appendChild(doc.createElement("link")).appendChild(doc.createTextNode(it["archive_link"]))
    item_el.appendChild(doc.createElement("guid")).appendChild(doc.createTextNode(it["orig_link"]))
    item_el.appendChild(doc.createElement("description")).appendChild(doc.createTextNode(it["summary"]))
    pubdate = email.utils.format_datetime(it["published_dt"])
    item_el.appendChild(doc.createElement("pubDate")).appendChild(doc.createTextNode(pubdate))
    if it.get("thumbnail"):
        thumb_el = doc.createElementNS(MEDIA_NS, "media:thumbnail")
        thumb_el.setAttribute("url", it["thumbnail"])
        item_el.appendChild(thumb_el)

with open(OUTPUT_FILE, "wb") as f:
    f.write(doc.toxml(encoding="utf-8"))

print(f"✅ combined.xml written: {len(new_entries)} new + {len(existing_entries)} existing → {len(all_entries)} total.")
