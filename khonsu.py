import discord
import logging
import asyncio
import json
import tweepy
from datetime import datetime, timezone, timedelta
from time import ctime, perf_counter
import re
import threading
import posixpath
import httpx
from urllib.parse import urlsplit, unquote, parse_qs
from io import BytesIO
from peony import PeonyClient
from bs4 import BeautifulSoup
from cssutils import parseStyle

logging.basicConfig (level = logging.WARNING)

bot = discord.Client ()

config = dict()
with open('config.json') as CONFIG:
    config = json.load(CONFIG)

#add your twitter keys here
consumer = config['consumer']
consumer_s = config['consumer_s']
token = config['token']
token_s = config['token_s']

auth = tweepy.OAuthHandler(consumer,consumer_s)
auth.set_access_token(token,token_s)
auth.secure = True
api = tweepy.API(auth)

live_scores_channel = list()
price_changes_channel = list()
team_news_channel = list()
stats_channel = list()

fpl = config['twitter_id']#add any twitter accounts id here
bap = config['twitter_id_2']
team_twitter_ids = config['team_twitter_ids']

last_tweet_used_id = None
last_tweet_used_bap_id = None

client = PeonyClient(consumer_key=consumer,
                     consumer_secret=consumer_s,
                     access_token=token,
                     access_token_secret=token_s)

watch_time_before_window = timedelta(minutes=2)
watch_time_after_window = timedelta(minutes=10)

watch_time_adjustment = timedelta(hours=1) - watch_time_after_window
min_watch_time_adjustment = watch_time_before_window + watch_time_after_window

watch_tweet_count = 5

sleep_time_seconds = 3

start_time = datetime.now(timezone.utc)

start_perf_counter = perf_counter()


async def task():
    global last_tweet_used_id, last_tweet_used_bap_id

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

    await get_all_fixtures()

    print("Ready.")

    while True:
        await asyncio.gather(
            get_latest_fixture_tweets(),
            get_latest_tweets(),
            get_latest_tweets_bap(),
            asyncio.sleep(sleep_time_seconds)
        )


def get_latest_time():
    return start_time + timedelta(seconds=perf_counter()-start_perf_counter)


def get_start_of_day(latest_time):
    return latest_time.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_event_fixtures(event_id):
    global fixtures, teams

    fixtures[event_id] = {}

    matches = []

    async with httpx.AsyncClient() as async_client:
        matches = (await async_client.get('https://fantasy.premierleague.com/api/fixtures/?event={}#/'.format(event_id))).json()

    latest_day = get_start_of_day(get_latest_time())

    for match in matches:
        kickoff_time = match['kickoff_time']
        watch_time = datetime.strptime(kickoff_time, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc) - watch_time_adjustment
        if (latest_day >= watch_time):
            continue

        if (watch_time not in fixtures[event_id]):
            fixtures[event_id][watch_time] = []

        for team in teams:
            if (team['id'] == match['team_h']):
                fixtures[event_id][watch_time].append(team['short_name'])

            if (team['id'] == match['team_a']):
                fixtures[event_id][watch_time].append(team['short_name'])


def update_latest_event_id():
    global fixtures, latest_event_id

    latest_event_id = None

    for event_id in sorted(fixtures):
        for watch_time in sorted(fixtures[event_id]):
            if (len(fixtures[event_id][watch_time]) > 0):
                latest_event_id = event_id
                return

            del fixtures[event_id][watch_time]

        del fixtures[event_id]


async def get_all_fixtures():
    global fixtures, teams

    fixtures = {}

    async with httpx.AsyncClient() as async_client:
        r = (await async_client.get('https://fantasy.premierleague.com/api/bootstrap-static/#/')).json()
    
    teams = r['teams']

    event_promises = []
    for event in r['events']:
        event_promises.append(get_event_fixtures(event['id']))

    await asyncio.gather(*event_promises)
    update_latest_event_id()


async def get_latest_fixtures():
    global latest_event_id

    update_latest_event_id()

    if latest_event_id:
        await get_event_fixtures(latest_event_id)


def url2filename(url):
    urlpath = urlsplit(url).path
    return posixpath.basename(unquote(urlpath))


async def send_url(chan, url, fileName=None, retry_count=0):
    global fixtures

    if (fileName is None):
        fileName = url2filename(url)

    try:
        async with httpx.AsyncClient() as async_client:
            r = await async_client.get(url)

            await chan.send(file=discord.File(BytesIO(await r.read()), filename=fileName))
    except Exception as e:
        if (retry_count < 5):
            await asyncio.sleep(1)
            await send_url(chan, url, fileName, retry_count + 1)
        else:
            raise


def get_card_thumbnail_url(card_div):
    playable_video_div = card_div.parent.find('div', class_='PlayableMedia-player')
    if playable_video_div is None:
        return

    style = parseStyle(playable_video_div['style'])
    return style['background-image'].replace('url(', '').replace(')', '')


async def get_card_url(tweet_id):
    tweet = await client.api.statuses.show.get(id=tweet_id,tweet_mode='extended',include_card_uri='true')
    card_uri = tweet.get('card_uri')
    if card_uri is None:
        urls = tweet.entities.get('urls')
        if urls:
            card_uri = urls[0].url
        else:
            return

    tweet_url = '/{}/status/{}'.format(tweet.user.screen_name, tweet.id)
    async with httpx.AsyncClient(base_url='https://www.twitter.com') as async_client:
        r = await async_client.get(tweet_url)

        tweet_soup = BeautifulSoup(r.text, 'lxml')
        card_div = tweet_soup.find('div', attrs={'data-card-url': card_uri})
        if card_div is None:
            return

        card_thumbnail_url = get_card_thumbnail_url(card_div)
        if card_thumbnail_url:
            return card_thumbnail_url

        r = await async_client.get(card_div['data-src'])

        card_soup = BeautifulSoup(r.text, 'lxml')
        card_img = card_soup.find('img')
        if card_img:
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


async def send_picture_tweet(tweet, channel, watch_time=None, team_short_name=None):
    global fixtures, latest_event_id

    send_promises = []

    extended_entities = tweet.get('extended_entities', {})
    media = extended_entities.get('media')

    try:
        if media:
            for chan in channel:
                for entity in media:
                    url = entity['media_url']
                    send_promises.append(send_url(chan, url))
        else:
            url = await get_card_url(tweet.id)
            if url:
                fileName = get_card_url_fileName(url)
                for chan in channel:
                    send_promises.append(send_url(chan, url, fileName))

        await asyncio.gather(*send_promises)
        if team_short_name:
            print("Sent teams for {}".format(team_short_name))
    except Exception as e:
        if (watch_time and team_short_name):
            fixtures[latest_event_id][watch_time].append(team_short_name)
        print(e)


async def get_latest_fixture_tweets():
    global fixtures, latest_event_id

    latest_time = get_latest_time()
    latest_day = get_start_of_day(latest_time)

    if (latest_time - latest_day <= timedelta(seconds=sleep_time_seconds)):
        await get_latest_fixtures()

    if (latest_event_id is None):
        return

    get_promises = []
    send_promises = []

    for watch_time in sorted(fixtures[latest_event_id]):
        if (latest_time > watch_time):
            fixtures[latest_event_id][watch_time].clear()
        else:
            team_short_names = fixtures[latest_event_id][watch_time]
            for team_short_name in team_short_names:
                get_promises.append(get_latest_team_tweets(watch_time, team_short_name, send_promises))

    await asyncio.gather(*get_promises)
    await asyncio.gather(*send_promises)


async def send_message(chan, embed_, retry_count=0):
    try:
        await chan.send(embed=embed_)
    except Exception as e:
        if (retry_count < 5):
            await asyncio.sleep(1)
            await send_message(chan, embed_, retry_count + 1)
        else:
            print(e)


async def send_tweet(tweet):
    latest = tweet.full_text
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


async def get_latest_team_tweets(watch_time, team_short_name, send_promises):
    global fixtures, latest_event_id

    latest_time = get_latest_time()

    min_watch_time = watch_time - min_watch_time_adjustment
    team_short_names = fixtures[latest_event_id][watch_time]

    if latest_time < min_watch_time:
        return

    try:
        team_short_names.remove(team_short_name)

        twitter_id = team_twitter_ids[team_short_name]
        tweet_list = await client.api.statuses.user_timeline.get(user_id=twitter_id,page=1,count=watch_tweet_count,tweet_mode='extended',include_rts='false')
        for tweet in reversed(tweet_list):
            created_at = datetime.strptime(tweet.created_at, '%a %b %d %H:%M:%S %z %Y').replace(tzinfo=timezone.utc)
            if (created_at >= min_watch_time):
                send_promises.append(send_picture_tweet(tweet, team_news_channel, watch_time, team_short_name))
                return

        team_short_names.append(team_short_name)
    except Exception as e:
        team_short_names.append(team_short_name)
        print(e)


async def get_latest_tweets():
    global last_tweet_used_id

    try:
        if last_tweet_used_id is None:
            last_tweet_used_id = (await client.api.statuses.user_timeline.get(user_id=fpl,page=1,count=1,include_rts='false'))[0].id

        tweet_promises = []

        tweet_list = await client.api.statuses.user_timeline.get(user_id=fpl,page=1,count=20,tweet_mode='extended',include_rts='false',since_id=last_tweet_used_id)
        for tweet in tweet_list:
            tweet_promises.append(send_tweet(tweet))
            if (tweet.id > last_tweet_used_id):
                last_tweet_used_id = tweet.id

        await asyncio.gather(*tweet_promises)
    except Exception as e:
        print(e)


async def send_tweet_bap(tweet):
    latest_bap = tweet.full_text
    is_Lineups = re.search('Lineups', latest_bap, re.M)
    is_Stats = re.search('Stats', latest_bap, re.M)
    if (is_Lineups or is_Stats):
        if is_Lineups:
            print("@FPLStatus lineups")
            channel = team_news_channel
        else:
            print("@FPLStatus stats")
            channel = stats_channel

        await send_picture_tweet(tweet, channel)
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
    global last_tweet_used_bap_id

    try:
        if last_tweet_used_bap_id is None:
            last_tweet_used_bap_id = (await client.api.statuses.user_timeline.get(user_id=bap,page=1,count=1,include_rts='false'))[0].id

        tweet_promises = []

        tweet_list = await client.api.statuses.user_timeline.get(user_id=bap,page=1,count=20,tweet_mode='extended',include_rts='false',since_id=last_tweet_used_bap_id)
        for tweet in tweet_list:
            tweet_promises.append(send_tweet_bap(tweet))
            if (tweet.id > last_tweet_used_bap_id):
                last_tweet_used_bap_id = tweet.id

        await asyncio.gather(*tweet_promises)
    except Exception as e:
        print(e)


@bot.event
async def on_message(m):
    if isinstance(m.channel, discord.DMChannel):
        tweet_id = int(m.content)
        tweet = await client.api.statuses.show.get(id=tweet_id,tweet_mode='extended')
        if tweet.user.id_str == fpl:
            await send_tweet(tweet)
        elif tweet.user.id_str == bap:
            await send_tweet_bap(tweet)

bot.loop.create_task(task())
bot.run(config['discord_token'])
