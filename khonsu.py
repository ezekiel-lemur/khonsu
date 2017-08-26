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

#add your twitter keys here
consumer = ""
consumer_s = ""
token = ""
token_s = ""

auth = tweepy.OAuthHandler(consumer,consumer_s)
auth.set_access_token(token,token_s)
auth.secure = True
api =tweepy.API(auth)

channel = None

@bot.event
async def on_ready ():
    global channel
    channel = bot.get_channel ("351055628246188032") # add channel id here (enter dev mode on discord & right click and copy it)
    if channel is not None:
        print('Found tweet channel')
    else:
        print('Didnt find tweet channel')
    print("Ready.")
    while True:
        await get_latest_tweet()
        sleep(5)

fpl = 761568335138058240 #add any twitter accounts id here

last_tweet_used = None

async def get_latest_tweet():
     tweet_list = api.user_timeline(id=fpl,count=1,page=1)
     tweet = tweet_list[0]
     latest = tweet.text
     print(latest)
     global last_tweet_used
     is_goal = re.search('Goal', latest, re.M|re.I) 
     is_assist = re.search('Assist', latest, re.M|re.I)
     is_one =  re.search('RED', latest, re.M|re.I)
     if ((is_goal and is_assist) or is_one) and (latest !=  last_tweet_used):
               print("This is it working")
               await bot.send_message (channel, latest)
               last_tweet_used = latest
               print("sent")
               print(channel)
     
    
    

bot.run ('') #add your discord token here
