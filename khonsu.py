import discord
import logging
import asyncio
import json
from contextlib import closing
from socket import socket, AF_INET, SOCK_DGRAM
from struct import unpack, calcsize
from datetime import datetime, timezone
from pandas import Timestamp, Timedelta
from time import perf_counter_ns
from collections import deque
import re
import posixpath
import ssl
import sys
import aiohttp
import httpx
import random
from fake_useragent import UserAgent
from urllib.parse import urlsplit, unquote, parse_qs
from requests_html import HTML
from io import BytesIO
from bs4 import BeautifulSoup
from lxml.etree import ParserError

NTP_PACKET_FORMAT = '!12I'
NTP_DELTA = 2208988800 # 1970-01-01 00:00:00
NTP_QUERY = b'\x1b' + 47 * b'\0'
NTP_HOST = 'pool.ntp.org'
NTP_PORT = 123

tweets_url = 'https://mobile.twitter.com/search'
twitter_params = {
    "f": "tweets",
    "include_available_features": "1", 
    "include_entities": "1",
    "vertical": "default",
    "src": "unkn",
    "reset_error_state": "false"
}

twitter_headers = {
    "X-Requested-With": "XMLHttpRequest"
}

logging.basicConfig(level = logging.WARNING)

ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
conn = aiohttp.TCPConnector(ssl=ssl_context,enable_cleanup_closed=True,force_close=True)

bot = discord.Client(connector=conn)

config = dict()
with open('config.json') as CONFIG:
    config = json.load(CONFIG)

live_scores_channel = list()
price_changes_channel = list()
team_news_channel = list()
stats_channel = list()

fpl_name = config['twitter_name']
bap_name = config['twitter_name_2']
team_twitter_names = config['team_twitter_names']

watch_delta_before_window = Timedelta(seconds=30)
watch_delta_after_window = Timedelta(minutes=6)

watch_delta_adjustment = Timedelta(hours=1) - watch_delta_after_window
min_watch_delta_adjustment = watch_delta_before_window + watch_delta_after_window

sleep_time_seconds = 3

refresh_daily_time = Timestamp(-NTP_DELTA, unit="s", tz="UTC").replace(hour=0, minute=0)

def get_ntp_time(host='pool.ntp.org', port=123):
    global start_perf_counter

    with closing(socket(AF_INET, SOCK_DGRAM)) as s:
        s.sendto(NTP_QUERY, (host, port))
        recv_data, address = s.recvfrom(1024)

    start_perf_counter = perf_counter_ns()
    unpacked = unpack(NTP_PACKET_FORMAT, recv_data[0:calcsize(NTP_PACKET_FORMAT)])
    return unpacked[10] + float(unpacked[11]) / 2**32 - NTP_DELTA


async def task():
    global last_tweet_used_id, last_tweet_used_bap_id, start_time, start_ts

    await bot.wait_until_ready()

    for chan in config['live_scores_channels']:
        c = bot.get_channel(chan)
        if c:
            live_scores_channel.append(c)
            print('Added {}@{} for live scores'.format(c.name, 'FantasyPL'))
        else:
            print('Couldn\'t find channel {}'.format(chan))

    for chan in config['price_changes_channels']:
        c = bot.get_channel(chan)
        if c:
            price_changes_channel.append(c)
            print('Added {}@{} for price changes'.format(c.name, 'FantasyPL'))
        else:
            print('Couldn\'t find channel {}'.format(chan))

    for chan in config['team_news_channels']:
        c = bot.get_channel(chan)
        if c:
            team_news_channel.append(c)
            print('Added {}@{} for team news'.format(c.name, 'FantasyPL'))
        else:
            print('Couldn\'t find channel {}'.format(chan))

    for chan in config['stats_channels']:
        c = bot.get_channel(chan)
        if c:
            stats_channel.append(c)
            print('Added {}@{} for stats'.format(c.name, 'FantasyPL'))
        else:
            print('Couldn\'t find channel {}'.format(chan))

    start_time = Timestamp(get_ntp_time(), unit="s", tz="UTC")
    start_ts = int(start_time.timestamp())
    last_tweet_used_id = None
    last_tweet_used_bap_id = None

    async with aiohttp.ClientSession(connector=conn) as session:
        await get_all_fixtures(session)

        print("Ready.")

        while True:
            await asyncio.gather(
                #get_latest_fixture_tweets(session),
                get_latest_tweets(),
                get_latest_tweets_bap(),
                asyncio.sleep(sleep_time_seconds)
            )
            await bot.wait_until_ready()


def get_latest_time():
    return start_time + Timedelta(nanoseconds=perf_counter_ns()-start_perf_counter)


def get_start_of_day(latest_time):
    return latest_time.replace(hour=0, minute=0, second=0, microsecond=0, nanosecond=0)


def get_refresh_time(latest_time):
    return latest_time.replace(hour=refresh_daily_time.hour, minute=refresh_daily_time.minute, second=refresh_daily_time.second, microsecond=0, nanosecond=0)


def get_event_fixtures(event_matches):
    global fixtures, teams

    fixtures = {}

    latest_day = get_start_of_day(get_latest_time())

    for match in event_matches:
        kickoff_time = datetime.strptime(match['kickoff_time'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        watch_time = Timestamp(kickoff_time) - watch_delta_adjustment
        if (latest_day >= watch_time):
            continue

        if (watch_time not in fixtures):
            fixtures[watch_time] = { 'teams': [] }

        for team in teams:
            if team['id'] == match['team_h'] or team['id'] == match['team_a']:
                fixtures[watch_time]['teams'].append(team['short_name'])
                fixtures[watch_time][team['short_name']] = 0

    return len(fixtures) > 0


async def get_all_fixtures(session):
    global fixtures, event_ids, teams

    fixtures = {}
    event_ids = deque([])

    async with session.get('https://fantasy.premierleague.com/api/bootstrap-static/', skip_auto_headers=['User-Agent']) as resp:
        bootstrap = await resp.json()

    async with session.get('https://fantasy.premierleague.com/api/fixtures/', skip_auto_headers=['User-Agent']) as resp:
        all_matches = await resp.json()

    event_matches_dict = {}
    for match in all_matches:
        event_id = match['event']
        if event_id is None:
            continue

        if (event_id not in event_matches_dict):
            event_matches_dict[event_id] = []

        event_matches_dict[event_id].append(match)

    teams = bootstrap['teams']

    for event in bootstrap['events']:
        event_id = event['id']
        if (len(fixtures) > 0 or (event_id in event_matches_dict and get_event_fixtures(event_matches_dict[event_id]))):
            event_ids.append(event_id)


def get_latest_event_id():
    global fixtures, event_ids

    if (len(event_ids) == 0):
        return

    for watch_time in sorted(fixtures):
        if (len(fixtures[watch_time]['teams']) > 0):
            return event_ids[0]

        del fixtures[watch_time]

    event_ids.popleft()
    if (len(event_ids) == 0):
        return

    return event_ids[0]


async def get_latest_fixtures(session):
    latest_event_id = get_latest_event_id()

    if latest_event_id is None:
        return

    params = { 'event': latest_event_id }

    async with session.get('https://fantasy.premierleague.com/api/fixtures', params=params, skip_auto_headers=['User-Agent']) as resp:
        event_matches = await resp.json()
    
    get_event_fixtures(event_matches)


def url2filename(url):
    urlpath = urlsplit(url).path
    return posixpath.basename(unquote(urlpath))


async def send_url(chan, url, fileName=None):
    global fixtures

    if (fileName is None):
        fileName = url2filename(url)

    retry_count = 0
    while True:
        try:
            async with httpx.AsyncClient(base_url='https://www.twitter.com') as client:
                r = await client.get(url)
        
            await chan.send(file=discord.File(BytesIO(r.read()), filename=fileName))
            return
        except Exception as e:
            if (retry_count < 5):
                await asyncio.sleep(1)
            else:
                raise


async def get_card_url(tweet):
    video_nodes = tweet.find(".PlayableMedia-player")
    for node in video_nodes:
        styles = node.attrs["style"].split()
        for style in styles:
            if style.startswith("background-image"):
                tmp = style.split("url('")[-1]
                video_thumbnail = tmp.replace("')", "")
                return video_thumbnail

    cards = [
        card_node.attrs["data-src"]
        for card_node in tweet.find(".card-type-promo_website")
    ]

    if len(cards) == 0:
        return

    async with httpx.AsyncClient(base_url='https://www.twitter.com') as client:
        r = await client.get(cards[0])

    card_soup = BeautifulSoup(r.text, 'lxml')
    
    card_img = card_soup.find('img')
    return card_img['data-src']


def get_card_url_fileName(url):
    url_qs = urlsplit(url).query
    fileName = url2filename(url)

    if url_qs is None:
        return fileName

    parsed_qs = parse_qs(url_qs)
    if parsed_qs.get('format') is None:
        return fileName

    image_fmt = parsed_qs['format'][0]
    return '{}.{}'.format(fileName, image_fmt)


async def send_media_tweet(tweet, channel, team_short_name=None):
    global fixtures

    send_promises = []

    media = [
        photo_node.find("div", {"class": "media"}).find("img")["src"].replace(":small", "")
        for photo_node in tweet.find_all("div", {"class": "card-photo"})
    ]

    try:
        if len(media) > 0:
            for chan in channel:
                for url in media:
                    send_promises.append(send_url(chan, url))
        else:
            url = await get_card_url(tweet)
            if url is not None:
                fileName = get_card_url_fileName(url)
                for chan in channel:
                    send_promises.append(send_url(chan, url, fileName))

        if len(send_promises) == 0:
            return False

        await asyncio.gather(*send_promises)
        if team_short_name is not None:
            print("Sent teams for {}".format(team_short_name))
        return True
    except Exception as e:
        print("Error in send_media_tweet")
        print(e)


async def get_latest_fixture_tweets(session):
    global fixtures

    latest_time = get_latest_time()
    refresh_time = get_refresh_time(latest_time)

    if (latest_time - refresh_time <= Timedelta(seconds=sleep_time_seconds)):
        await get_latest_fixtures(session)
    
    get_promises = []

    for watch_time in sorted(fixtures):
        if (latest_time > watch_time):
            fixtures[watch_time]['teams'].clear()
        else:
            team_short_names = fixtures[watch_time]['teams']
            for team_short_name in team_short_names:
                get_promises.append(get_latest_team_tweets(watch_time, team_short_name))

    await asyncio.gather(*get_promises)


async def send_message(chan, embed_, retry_count=0):
    try:
        await chan.send(embed=embed_)
    except Exception as e:
        if (retry_count < 5):
            await asyncio.sleep(1)
            await send_message(chan, embed_, retry_count + 1)
        else:
            print("Error in send_message")
            print(e)


async def send_tweet(text):
    latest = text
    is_goal = re.search('GOAL', latest, re.M)
    is_Goal = re.search('Goal', latest, re.M)
    is_assist = re.search('ASSIST', latest, re.M)
    is_Assist = re.search('Assist', latest, re.M)
    is_Red = re.search('Red card', latest, re.M|re.I)
    is_scout = re.search('scout', latest, re.M|re.I)
    is_baps = re.search('BONUS', latest, re.M)
    is_prov = re.search('STANDS', latest, re.M)
    is_pen = re.search('Penalty miss', latest, re.M)

    if (((is_goal and is_assist) or (is_Goal and is_Assist) or is_Red or is_pen or (is_baps and is_prov)) and not is_scout):
        print("@OfficialFPL Update")
        chan_promises = []
        for chan in live_scores_channel:
            embed_ = discord.Embed (description = latest)
            chan_promises.append(send_message(chan, embed_))

        await asyncio.gather(*chan_promises)


async def get_latest_team_tweets(watch_time, team_short_name):
    global fixtures

    latest_time = get_latest_time()

    min_watch_time = watch_time - min_watch_delta_adjustment
    team_short_names = fixtures[watch_time]['teams']

    if latest_time < min_watch_time:
        return

    try:
        twitter_name = team_twitter_names[team_short_name]

        min_watch_ts = int(min_watch_time.timestamp())
        min_tweet_ts = fixtures[watch_time][team_short_name]
        if min_tweet_ts == 0:
            min_tweet_ts = min_watch_ts

        max_tweet_ts = int(watch_time.timestamp())
        params = twitter_params.copy()
        params['q'] = f'from:{twitter_name} exclude:nativeretweets exclude:retweets since:{min_tweet_ts + 1} until:{max_tweet_ts}'

        async with httpx.AsyncClient(base_url='https://mobile.twitter.com') as client:
            r = await client.get(tweets_url, params=params, headers=twitter_headers)

        fixtures[watch_time][team_short_name] = int(get_latest_time().timestamp())

        soup = BeautifulSoup(r, "html.parser")
        tweets = soup.find_all("table", "tweet")

        tweet_list = []
        for tweet in tweets:
            tweet_id = tweet.find("div", {"class": "tweet-text"})["data-id"];
            tweet_list.append({ "tweet_id": tweet_id, "tweet": tweet })

        for tweet in sorted(tweet_list, key=lambda tweet: tweet["tweet_id"], reverse=True):
            tweet_sent = await send_media_tweet(tweet["tweet"], team_news_channel, team_short_name)

    except Exception as e:
        print("Error in get_latest_team_tweets")
        print(e)


async def get_latest_tweets():
    global start_ts, last_tweet_used_id

    try:
        tweet_promises = []

        twitter_name = fpl_name

        max_tweet_ts = int(get_latest_time().timestamp())

        params = twitter_params.copy()
        params['q'] = f' from:{twitter_name} exclude:nativeretweets exclude:retweets since:{start_ts} until:{max_tweet_ts}'

        async with httpx.AsyncClient(base_url='https://mobile.twitter.com') as client:
            r = await client.get(tweets_url, params=params, headers=twitter_headers)
        
        soup = BeautifulSoup(r, "html.parser")
        tweets = soup.find_all("table", "tweet")

        max_tweet_id = None
        for tweet in tweets:
            text = tweet.find("div", {"class": "tweet-text"}).find("div", {"class": "dir-ltr"}).text
            tweet_id = int(tweet.find("div", {"class": "tweet-text"})["data-id"])
            if last_tweet_used_id is None or tweet_id > last_tweet_used_id:
                print(text)
                tweet_promises.append(send_tweet(text))
                if max_tweet_id is None or tweet_id > max_tweet_id:
                    max_tweet_id = tweet_id

        if max_tweet_id is not None:
            last_tweet_used_id = max_tweet_id

        await asyncio.gather(*tweet_promises)

    except Exception as e:
        print("Error in get_latest_tweets")
        print(e)


async def send_tweet_bap(text, tweet):
    latest_bap = text
    is_Lineups = re.search('Lineups', latest_bap, re.M)
    is_Stats = re.search('Stats', latest_bap, re.M)
    if (is_Lineups or is_Stats):
        if is_Lineups:
            print("@FPLStatus lineups")
            channel = team_news_channel
        else:
            print("@FPLStatus stats")
            channel = stats_channel

        await send_media_tweet(tweet, channel)
    else:
        is_Pen = re.search('Penalty', latest_bap, re.M)
        is_Goal = re.search('Goal', latest_bap, re.M)
        is_Red = re.search('Red Card', latest_bap, re.M)
        is_Mod = re.search('Modified', latest_bap, re.M)
        is_prov = re.search('Provisional Bonus', latest_bap, re.M)
        is_confirmed = re.search('Confirmed Bonus', latest_bap, re.M)
        is_Rises = re.search('Price Rises', latest_bap, re.M)
        is_Falls = re.search('Price Falls', latest_bap, re.M)

        chan_promises = []

        if (is_Pen or is_Goal or is_Red or is_Mod or is_prov or is_confirmed):
            print("@FPLStatus points/baps")
            for chan in live_scores_channel:
                embed_ = discord.Embed (description = latest_bap)
                chan_promises.append(send_message(chan, embed_))

        if (is_Rises or is_Falls):
            print("@FPLStatus price rises/falls")
            for chan in price_changes_channel:
                embed_ = discord.Embed (description = latest_bap)
                chan_promises.append(send_message(chan, embed_))

        await asyncio.gather(*chan_promises)        
        

async def get_latest_tweets_bap():
    global start_ts, last_tweet_used_bap_id

    try:
        tweet_promises = []

        twitter_name = bap_name

        max_tweet_ts = int(get_latest_time().timestamp())

        params = twitter_params.copy()
        params['q'] = f' from:{twitter_name} exclude:nativeretweets exclude:retweets since:{start_ts} until:{max_tweet_ts}'

        async with httpx.AsyncClient(base_url='https://mobile.twitter.com') as client:
            r = await client.get(tweets_url, params=params, headers=twitter_headers)
        
        soup = BeautifulSoup(r, "html.parser")
        tweets = soup.find_all("table", "tweet")

        max_tweet_id = None
        for tweet in tweets:
            text = tweet.find("div", {"class": "tweet-text"}).find("div", {"class": "dir-ltr"}).text
            tweet_id = int(tweet.find("div", {"class": "tweet-text"})["data-id"])
            if last_tweet_used_bap_id is None or tweet_id > last_tweet_used_bap_id:
                print(text)
                tweet_promises.append(send_tweet_bap(text, tweet))
                if max_tweet_id is None or tweet_id > max_tweet_id:
                    max_tweet_id = tweet_id

        if max_tweet_id is not None:
            last_tweet_used_bap_id = max_tweet_id

        await asyncio.gather(*tweet_promises)

    except Exception as e:
        print("Error in get_latest_tweets_bap")
        print(e)


bot.loop.create_task(task())
bot.run(config['discord_token'], reconnect=True)
