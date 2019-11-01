import discord
import logging
import asyncio
import json
import tweepy
from socket import AF_INET, SOCK_DGRAM, socket
from struct import unpack
from datetime import datetime, timezone, timedelta
from time import ctime, sleep
import re
import threading
import wget
import requests
import os
import httpx

logging.basicConfig (level = logging.INFO)

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

REF_TIME_1970=2208988800

client = socket(AF_INET, SOCK_DGRAM)
data = b'\x1b' + 47 * b'\0'

watch_time_adjustment = timedelta(hours=1) - timedelta(seconds=30)

def tweet_callback(fut):
    try:
        tweet_list = fut.result()
    except Exception as e:
        print("Error processing tweets: {}".format(e))


def fixtures_callback(fut):
    global fixtures

    try:
        fixtures = fut.result()
    except Exception as e:
        print("Error getting fixtures: {}".format(e))
    
    
def file_callback(fut):
    try:
        fileName = fut.result()
        os.remove(fileName)
    except Exception as e:
        print("Error sending file: {}".format(e))


def latest_time_callback(fut):
    global latest_time, fixtures

    try:
        latest_time = fut.result()

        if (latest_time is not None and latest_time.hour == 0 and latest_time.minute == 0 and latest_time.seconds < 5):
            futurefixtures = asyncio.ensure_future(get_latest_fixtures())
            futurefixtures.add_done_callback(fixtures_callback)
        else:
            next_watch_time = None
            twitter_ids = None

            for watch_time in sorted(fixtures):
                if (watch_time < latest_time):
                    del fixtures[watch_time]
                else:
                    next_watch_time = watch_time - timedelta(minutes=1)
                    twitter_ids = fixtures[watch_time]
                    break

            if next_watch_time is not None and latest_time >= next_watch_time:
                for twitter_id in reversed(twitter_ids):
                    tweet = api.user_timeline(id=twitter_id,count=1,page=1,tweet_mode='extended',include_rts='false')[0]
                    created_at = tweet.created_at.replace(tzinfo=timezone.utc)
                    if (created_at >= next_watch_time):
                        twitter_ids.remove(twitter_id)
                        media = tweet.extended_entities.get('media', [])
                        for chan in team_news_channel:
                            for entity in media:
                                fileName = wget.download(entity['media_url'])
                            
                                future = asyncio.ensure_future(send_file(chan, fileName, 0))
                                future.add_done_callback(file_callback)

    except Exception as e:
        print("Error getting latest time: {}".format(e))


async def task():
    global channel, fpl, bap, last_tweet_used_id, last_tweet_used_bap_id, fixtures

    await bot.wait_until_ready()

    for chan in config['live_scores_channels']:
        c = bot.get_channel(chan)
        if c is not None:
            live_scores_channel.append(c)
            print('Added {}@{} for live scores'.format(c.name, 'FantasyPL'))
        else:
            print('Couldn\'t find channel {}'.format(chan))

    for chan in config['price_changes_channels']:
        c = bot.get_channel(chan)
        if c is not None:
            price_changes_channel.append(c)
            print('Added {}@{} for price changes'.format(c.name, 'FantasyPL'))
        else:
            print('Couldn\'t find channel {}'.format(chan))

    for chan in config['team_news_channels']:
        c = bot.get_channel(chan)
        if c is not None:
            team_news_channel.append(c)
            print('Added {}@{} for team news'.format(c.name, 'FantasyPL'))
        else:
            print('Couldn\'t find channel {}'.format(chan))

    for chan in config['stats_channels']:
        c = bot.get_channel(chan)
        if c is not None:
            stats_channel.append(c)
            print('Added {}@{} for stats'.format(c.name, 'FantasyPL'))
        else:
            print('Couldn\'t find channel {}'.format(chan))

    print("Ready.")
    if last_tweet_used_id is None:
        last_tweet_used_id = api.user_timeline(id=fpl,count=1,page=1,include_rts='false')[0].id

    if last_tweet_used_bap_id is None:
        last_tweet_used_bap_id = api.user_timeline(id=bap,count=1,page=1,include_rts='false')[0].id

    fixtures = await get_latest_fixtures()

    while True:
        futuretime = asyncio.ensure_future(get_latest_time())
        futuretime.add_done_callback(latest_time_callback)

        future = asyncio.ensure_future(get_latest_tweets())
        future.add_done_callback(tweet_callback)
        futurebap = asyncio.ensure_future(get_latest_tweets_bap())
        futurebap.add_done_callback(tweet_callback)

        await asyncio.sleep(5)


async def get_latest_fixtures():
    fixtures_dict = {}
    async with httpx.AsyncClient() as async_client:
        r = (await async_client.get('https://fantasy.premierleague.com/api/bootstrap-static/#/')).json()
        events = r['events']
        teams = r['teams']
        for event in events:
            if (event['finished'] == False):
                fixtures_r = (await async_client.get('https://fantasy.premierleague.com/api/fixtures/?event={}#/'.format(event['id']))).json()
                for match in fixtures_r:
                    if (match['started'] == False):
                        kickoff_time = match['kickoff_time']
                        watch_time_dt = datetime.strptime(kickoff_time, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc) - watch_time_adjustment
                        if (watch_time_dt not in fixtures_dict):
                            fixtures_dict[watch_time_dt] = []

                        for team in teams:
                            if (team['id'] == match['team_h']):
                                fixtures_dict[watch_time_dt].append(team_twitter_ids[team['short_name']])

                            if (team['id'] == match['team_a']):
                                fixtures_dict[watch_time_dt].append(team_twitter_ids[team['short_name']])

                return fixtures_dict


async def get_latest_time():
    await bot.loop.sock_connect(client, ('0.de.pool.ntp.org', 123))
    await bot.loop.sock_sendall(client, data)
    recv_data = await bot.loop.sock_recv(client, 1024)
    if recv_data:
        t = unpack('!12I', recv_data)[10]
        t -= REF_TIME_1970

    return datetime.fromtimestamp(t, timezone.utc)


async def send_file(chan, fileName, retry_count):
    try:
        await asyncio.sleep(3)
        await bot.send_file(chan, fileName)
        return fileName
    except Exception as e:
        if (retry_count < 5):
            await asyncio.sleep(1)
            return await send_file(chan, fileName, retry_count + 1)
        else:
            #os.remove(fileName)
            raise e


async def send_message(chan, embed_, retry_count):
    try:
        return await bot.send_message(chan, embed=embed_)
    except Exception as e:
        if (retry_count < 5):
            await asyncio.sleep(1)
            return await send_message(chan, embed_, retry_count + 1)
        else:
            raise e


def mesg_callback(fut):
    try:
        mesg = fut.result()
    except Exception as e:
        print("Error sending message: {}".format(e))


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
        print("Reached")
        for chan in live_scores_channel:
            embed_ = discord.Embed (description = latest)
            future = asyncio.ensure_future(send_message(chan, embed_, 0))
            future.add_done_callback(mesg_callback)


async def get_latest_tweets():
    global last_tweet_used_id

    tweet_list = api.user_timeline(id=fpl,count=20,page=1,tweet_mode='extended',include_rts='false',since_id=last_tweet_used_id)

    for tweet in tweet_list:
        if (tweet.id > last_tweet_used_id):
            last_tweet_used_id = tweet.id

        await send_tweet(tweet)

    return tweet_list

#get teams/points/provisional/confirmed baps from separate account

async def send_tweet_bap(tweet):
    latest_bap = tweet.full_text
    is_Lineups = re.search('Lineups', latest_bap, re.M)
    is_Stats = re.search('Stats', latest_bap, re.M)
    if (is_Lineups or is_Stats):
        media = tweet.extended_entities.get('media', [])
        if is_Lineups:
            print("got lineups")
            channel = team_news_channel
        else:
            print("got stats")
            channel = stats_channel

        for chan in channel:
            for entity in media:
                fileName = wget.download(entity['media_url'])
            
                future = asyncio.ensure_future(send_file(chan, fileName, 0))
                future.add_done_callback(file_callback)
    else:
        is_Pen = re.search('Penalty', latest_bap, re.M)
        is_Goal = re.search('Goal', latest_bap, re.M)
        is_Red = re.search('Red Card', latest_bap, re.M)
        is_Mod = re.search('Modified', latest_bap, re.M)
        is_prov = re.search('Provisional Bonus', latest_bap, re.M)
        is_confirmed = re.search('Confirmed Bonus', latest_bap, re.M)
        is_Rises = re.search('Price Rises', latest_bap, re.M)
        is_Falls = re.search('Price Falls', latest_bap, re.M)

        if (is_Pen or is_Goal or is_Red or is_Mod or is_prov or is_confirmed):
            print("got points/baps or price rises/falls")
            for chan in live_scores_channel:
                embed_ = discord.Embed (description = latest_bap)
                future = asyncio.ensure_future(send_message(chan, embed_, 0))
                future.add_done_callback(mesg_callback)
        
        if (is_Rises or is_Falls):
            print("got price rises/falls")
            for chan in price_changes_channel:
                embed_ = discord.Embed (description = latest_bap)
                future = asyncio.ensure_future(send_message(chan, embed_, 0))
                future.add_done_callback(mesg_callback)

async def get_latest_tweets_bap():
    global last_tweet_used_bap_id

    tweet_list = api.user_timeline(id=bap,count=20,page=1,tweet_mode='extended',include_rts='false',since_id=last_tweet_used_bap_id)

    for tweet in tweet_list:
        if (tweet.id > last_tweet_used_bap_id):
            last_tweet_used_bap_id = tweet.id

        await send_tweet_bap(tweet)

    return tweet_list


def handle_exit():
    print("Handling")
    bot.loop.run_until_complete(bot.logout())
    for t in asyncio.Task.all_tasks(loop=bot.loop):
        if t.done():
            t.exception()
            continue
        t.cancel()
        try:
            bot.loop.run_until_complete(asyncio.wait_for(t, 5, loop=bot.loop))
            t.exception()
        except asyncio.InvalidStateError:
            pass
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            pass


while True:
    @bot.event
    async def on_message(m):
        if m.channel.is_private:
            tweet = api.get_status(int(m.content),tweet_mode='extended')
            if tweet.user.id_str == fpl:
                await send_tweet(tweet)
            elif tweet.user.id_str == bap:
                await send_tweet_bap(tweet)

    bot.loop.create_task(task())
    try:
        bot.loop.run_until_complete(bot.start(config['discord_token']))
    except SystemExit:
        handle_exit()
    except KeyboardInterrupt:
        handle_exit()
        bot.loop.close()
        print("Program ended")
        break
