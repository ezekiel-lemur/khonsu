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
with open('config.priv.json') as CONFIG:
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

@bot.event
async def on_ready ():
    global channel

    for chan in config['channels']:
        c = bot.get_channel(chan)
        if c is not None:
            channel.append(c)
            print('Added {}@{}'.format(c.name, 'FantasyPL'))
        else:
            print('Couldn\'t find channel {}'.format(chan))

    print("Ready.")
    while True:
        await get_latest_tweet()
        await get_latest_tweet_sky()
        await asyncio.sleep(5)


fpl = config['twitter_id']#add any twitter accounts id here
sky = config['twitter_id_2']
bap = config['twitter_id_3']

last_tweet_used = None
last_tweet_used_sky = None
last_tweet_used_bap = None

async def get_latest_tweet():
    global last_tweet_used

    tweet_list = api.user_timeline(id=fpl,count=1,page=1)
    tweet = tweet_list[0]
    latest = tweet.text

    is_goal = re.search('GOAL', latest, re.M)
    is_assist = re.search('ASSIST', latest, re.M)
    is_Goal = re.search('Goal', latest, re.M)
    is_Assist = re.search('Assist', latest, re.M)
    is_red =  re.search('RED', latest, re.M)
    is_scout = re.search('scout', latest, re.M|re.I)
    is_baps = re.search('BONUS', latest, re.M)
    is_prov = re.search('STANDS', latest, re.M)

    if (((is_goal and is_assist) or (is_Goal and is_Assist) or is_red or (is_baps and is_prov)) \
            and (latest !=  last_tweet_used)) and not is_scout:
        print("Reached")
        for chan in channel:
            embed_ = discord.Embed (description = latest)
            await bot.send_message (chan, embed=embed_)
            last_tweet_used = latest

#get team news from seperate account

async def get_latest_tweet_sky():
    global last_tweet_used_sky

    tweet_list = api.user_timeline(id=sky,count=1,page=1)
    tweet = tweet_list[0]
    latest_sky = tweet.text

    is_team_news = re.search('team v', latest_sky, re.M)
    is_xi = re.search('XI', latest_sky, re.M)


    if (is_team_news or is_xi) and (latest_sky !=  last_tweet_used_sky):
        print("got team news")
        for chan in channel:
            embed_ = discord.Embed (description = latest_sky)
            await bot.send_message (chan, embed=embed_)
            last_tweet_used_sky = latest_sky

#    else:
#        for chan in channel:
#            embed_ = discord.Embed (description = latest)
#            await bot.send_message (chan, embed=embed_)
#            last_tweet_used = latest

#get confirmed baps from separate account

async def get_latest_tweet_bap():
    global last_tweet_used_bap

    tweet_list - api.user_timeline(id=bap,count=1,page=1)
    tweet = tweet_list[0]
    latest_bap = tweet.text

    is_confirmed = re.search('Confirmed Bonus', latest_bap, re.M)

    if is_confirmed and (latest_bap !=  last_tweet_used_bap):
        print("got confirmed baps")
        for chan in channel:
            embed_ = discord.Embed (description = latest_bap)
            await bot.send_message (chan, embed=embed_)
            last_tweet_used_bap = latest_bap


bot.run (config['discord_token']) #add your discord token here
