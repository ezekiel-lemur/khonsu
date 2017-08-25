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

consumer = "key"
consumer_s = "key"
token = "key-key"
token_s = "key"

auth = tweepy.OAuthHandler(consumer,consumer_s)
auth.set_access_token(token,token_s)
auth.secure = True
api =tweepy.API(auth)

@bot.event
async def on_ready ():
    print("Ready.")

fpl = 761568335138058240

CHANNEL = bot.get_channel ("330048090029686786")
 
def get_latest_tweet():
     tweet_list = api.user_timeline(id=fpl,count=1,page=1)
     tweet = tweet_list[0]
     latest = tweet.text
     if re.search('the', latest, re.M|re.I) and \
             (re.search('Assist', latest, re.M|re.I) or \
             re.search('RED', latest, re.M|re.I)):
               bot.send_message (CHANNEL, latest) 
     threading.Timer(5, get_latest_tweet).start()
 
@bot.event
async def on_ready():
    print("Ready")
    get_latest_tweet()

bot.run ('key') # You can find the token where you created the bot account

