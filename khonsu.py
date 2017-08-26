import discord # Install it with pipe
import logging
import asyncio
import json
import tweepy
from time import sleep
import re
import threading

logging.basicConfig (level = logging.INFO)

bot = discord.Client ()

consumer = 
consumer_s = 
token = 
token_s = 

auth = tweepy.OAuthHandler(consumer,consumer_s)
auth.set_access_token(token,token_s)
auth.secure = True
api =tweepy.API(auth)

channel = None

@bot.event
async def on_ready ():
    global channel
    channel = bot.get_channel ("350673589143470086")
    if channel is not None:
        print('Found tweet channel')
    else:
        print('Didnt find tweet channel')
    print("Ready.")
    await get_latest_tweet()


fpl = 761568335138058240
 
async def get_latest_tweet():
     tweet_list = api.user_timeline(id=fpl,count=1,page=1)
     tweet = tweet_list[0]
     latest = tweet.text
     print(latest)
     is_goal = re.search('Goal', latest, re.M|re.I) 
     is_assist = re.search('Assist', latest, re.M|re.I)
     is_one =  re.search('is', latest, re.M|re.I)
     if (is_goal and is_assist) or is_one:
               print("This is it working")
               await bot.send_message (channel, latest) 
               print("sent")
               print(channel)
     threading.Timer(5, get_latest_tweet).start()
    
    

bot.run ('..')

