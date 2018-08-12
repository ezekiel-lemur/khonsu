import discord
import logging
import asyncio
import json
import tweepy
from time import sleep
import re
import threading

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

channel = list()

fpl = config['twitter_id']#add any twitter accounts id here
sky = config['twitter_id_2']
bap = config['twitter_id_3']

last_tweet_used_id = None
last_tweet_used_sky_id = None
last_tweet_used_bap_id = None


def tweet_callback(fut):
    try:
        tweet_list = fut.result()
    except Exception as e:
        print("Error processing tweets: {}".format(e))


async def task():
    global channel, fpl, sky, bap, last_tweet_used_id, last_tweet_used_sky_id, last_tweet_used_bap_id

    await bot.wait_until_ready()

    for chan in config['channels']:
        c = bot.get_channel(chan)
        if c is not None:
            channel.append(c)
            print('Added {}@{}'.format(c.name, 'FantasyPL'))
        else:
            print('Couldn\'t find channel {}'.format(chan))

    print("Ready.")
    if last_tweet_used_id is None:
        last_tweet_used_id = api.user_timeline(id=fpl,count=1,page=1)[0].id

    if last_tweet_used_sky_id is None:
        last_tweet_used_sky_id = api.user_timeline(id=sky,count=1,page=1)[0].id

    if last_tweet_used_bap_id is None:
        last_tweet_used_bap_id = api.user_timeline(id=bap,count=1,page=1)[0].id

    while True:
        future = asyncio.ensure_future(get_latest_tweets())
        future.add_done_callback(tweet_callback)
        futuresky = asyncio.ensure_future(get_latest_tweets_sky())
        futuresky.add_done_callback(tweet_callback)
        futurebap = asyncio.ensure_future(get_latest_tweets_bap())
        futurebap.add_done_callback(tweet_callback)
        await asyncio.sleep(5)


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
    is_assist = re.search('ASSIST', latest, re.M)
    is_Goal = re.search('Goal', latest, re.M)
    is_Assist = re.search('Assist', latest, re.M)
    is_red =  re.search('RED', latest, re.M)
    is_Red = re.search('Red card for', latest, re.M)
    is_scout = re.search('scout', latest, re.M|re.I)
    is_baps = re.search('BONUS', latest, re.M)
    is_prov = re.search('STANDS', latest, re.M)
    is_pen = re.search('Penalty miss', latest, re.M)

    if (((is_goal and is_assist) or (is_Goal and is_Assist) or is_red or is_Red or is_pen or (is_baps and is_prov)) and not is_scout):
        print("Reached")
        for chan in channel:
            embed_ = discord.Embed (description = latest)
            future = asyncio.ensure_future(send_message(chan, embed_, 0))
            future.add_done_callback(mesg_callback)


async def get_latest_tweets():
    global last_tweet_used_id

    tweet_list = api.user_timeline(id=fpl,count=20,page=1,tweet_mode='extended',since_id=last_tweet_used_id)

    for tweet in tweet_list:
        if (tweet.id > last_tweet_used_id):
            last_tweet_used_id = tweet.id

        await send_tweet(tweet)

    return tweet_list

#get team news from seperate account

async def send_tweet_sky(tweet):
    latest_sky = tweet.full_text
    is_team_news = re.search('team v', latest_sky, re.M)
    is_xi = re.search('XI', latest_sky, re.M)

    if (is_team_news or is_xi):
        print("got team news")
        for chan in channel:
            embed_ = discord.Embed (description = latest_sky)
            future = asyncio.ensure_future(send_message(chan, embed_, 0))
            future.add_done_callback(mesg_callback)


async def get_latest_tweets_sky():
    global last_tweet_used_sky_id

    tweet_list = api.user_timeline(id=sky,count=20,page=1,tweet_mode='extended',since_id=last_tweet_used_sky_id)

    for tweet in tweet_list:
        if (tweet.id > last_tweet_used_sky_id):
            last_tweet_used_sky_id = tweet.id

        await send_tweet_sky(tweet)

    return tweet_list

#get points/provisional/confirmed baps from separate account

async def send_tweet_bap(tweet):
    latest_bap = tweet.full_text
    is_Lineups = re.search('Lineups', latest_bap, re.M)
    is_Stats = re.search('Stats', latest_bap, re.M)
    if (is_Lineups or is_Stats):
        print("got lineups/stats")
        media = tweet.extended_entities.get('media', [])
        for entity in media:
            for chan in channel:
                embed_ = discord.Embed()
                embed_.set_image(url=entity['media_url'])
                future = asyncio.ensure_future(send_message(chan, embed_, 0))
                future.add_done_callback(mesg_callback)
    else:
        is_Pen = re.search('Penalty', latest_bap, re.M)
        is_Goal = re.search('Goal', latest_bap, re.M)
        is_Red = re.search('Red Card', latest_bap, re.M)
        is_Mod = re.search('Modified', latest_bap, re.M)
        is_prov = re.search('Provisional Bonus', latest_bap, re.M)
        is_confirmed = re.search('Confirmed Bonus', latest_bap, re.M)
        is_Avg = re.search('Averages', latest_bap, re.M)

        if (is_Pen or is_Goal or is_Red or is_Mod or is_prov or is_confirmed or is_Avg):
            print("got points/baps")
            for chan in channel:
                embed_ = discord.Embed (description = latest_bap)
                future = asyncio.ensure_future(send_message(chan, embed_, 0))
                future.add_done_callback(mesg_callback)


async def get_latest_tweets_bap():
    global last_tweet_used_bap_id

    tweet_list = api.user_timeline(id=bap,count=20,page=1,tweet_mode='extended',since_id=last_tweet_used_bap_id)

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
            elif tweet.user.id_str == sky:
                await send_tweet_sky(tweet)
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
