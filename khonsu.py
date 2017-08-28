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
            print('Added {}@{}'.format(c.name, c.server.name))
        else:
            print('Couldn\'t find channel {}'.format(chan))

    print("Ready.")
    while True:
        await get_latest_tweet()
        await asyncio.sleep(5)


fpl = config['twitter_id']#add any twitter accounts id here

last_tweet_used = None

async def get_latest_tweet():
    global last_tweet_used

    tweet_list = api.user_timeline(id=fpl,count=1,page=1)
    tweet = tweet_list[0]
    latest = tweet.text

    is_goal = re.search('Goal', latest, re.M|re.I)
    is_assist = re.search('Assist', latest, re.M|re.I)
    is_red =  re.search('RED', latest, re.M|re.I)
    is_scout = re.search('scout', latest, re.M|re.I)

    if (((is_goal and is_assist) or is_red) \
            and (latest !=  last_tweet_used)) and not is_scout:
        print("Reached")
        for chan in channel:
            embed_ = discord.Embed (description = latest)
            await bot.send_message (chan, embed=embed_)
            last_tweet_used = latest
#    else:
#        for chan in channel:
#            embed_ = discord.Embed (description = latest)
#            await bot.send_message (chan, embed=embed_)
#            last_tweet_used = latest


bot.run (config['discord_token']) #add your discord token here
