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

last_tweets_used = list()
last_tweets_used_sky = list()
last_tweets_used_bap = list()

@bot.event
async def on_ready ():
    global channel, fpl, sky, bap, last_tweet_used_id, last_tweet_used_sky_id, last_tweet_used_bap_id

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
        await get_latest_tweets()
        await get_latest_tweets_sky()
        await get_latest_tweets_bap()
        await asyncio.sleep(5)


async def get_latest_tweets():
    global last_tweets_used, last_tweet_used_id

    tweet_list = api.user_timeline(id=fpl,count=20,page=1,since_id=last_tweet_used_id)

    for tweet in tweet_list:
        latest_id = tweet.id
        if (latest_id > last_tweet_used_id):
            last_tweet_used_id = latest_id

        if latest_id not in last_tweets_used:
            latest = tweet.text
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
                    await bot.send_message (chan, embed=embed_)
                    # print(latest)
                    last_tweets_used.append(latest_id)

#get team news from seperate account

async def get_latest_tweets_sky():
    global last_tweets_used_sky, last_tweet_used_sky_id

    tweet_list = api.user_timeline(id=sky,count=20,page=1,tweet_mode='extended',since_id=last_tweet_used_sky_id)

    for tweet in tweet_list:
        latest_sky_id = tweet.id
        if (latest_sky_id > last_tweet_used_sky_id):
            last_tweet_used_sky_id = latest_sky_id

        if latest_sky_id not in last_tweets_used_sky:
            latest_sky = tweet.full_text
            is_team_news = re.search('team v', latest_sky, re.M)
            is_xi = re.search('XI', latest_sky, re.M)

            if (is_team_news or is_xi):
                print("got team news")
                for chan in channel:
                    embed_ = discord.Embed (description = latest_sky)
                    await bot.send_message (chan, embed=embed_)
                    # print(latest)
                    last_tweets_used_sky.append(latest_sky_id)

#    else:
#        for chan in channel:
#            embed_ = discord.Embed (description = latest)
#            await bot.send_message (chan, embed=embed_)
#            last_tweet_used = latest

#get provisional/confirmed baps from separate account

async def get_latest_tweets_bap():
    global last_tweets_used_bap, last_tweet_used_bap_id

    tweet_list = api.user_timeline(id=bap,count=20,page=1,since_id=last_tweet_used_bap_id)

    for tweet in tweet_list:
        latest_bap_id = tweet.id
        if (latest_bap_id > last_tweet_used_bap_id):
            last_tweet_used_bap_id = latest_bap_id

        if latest_bap_id not in last_tweets_used_bap:
            latest_bap = tweet.text
            is_prov = re.search('Provisional Bonus', latest_bap, re.M)
            is_confirmed = re.search('Confirmed Bonus', latest_bap, re.M)

            if (is_prov or is_confirmed):
                print("got baps")
                for chan in channel:
                    embed_ = discord.Embed (description = latest_bap)
                    await bot.send_message (chan, embed=embed_)
                    # print(latest)
                    last_tweets_used_bap.append(latest_bap_id)


bot.run (config['discord_token']) #add your discord token here
