#!/usr/bin/env python3
import requests
import sys, os, time
import configparser
from lxml import html
from dateutil import parser
import tweepy

def fail(message):
  print("ERROR: {}".format(message), file=sys.stderr)
  sys.exit(1)

# Read config file in
mydir = os.path.dirname(os.path.realpath(__file__))
configname = "config.txt"
configReader = configparser.RawConfigParser()
configReader.read("{}/{}".format(mydir, configname))

# Some defaults
config = {
  'baseurl': "https://www.lotro.com/en/forums/",
  'maxlen': "280",
}
for var in list(config.keys()) + ['consumer_key', 'consumer_secret', 'access_key', 'access_secret']:
  try:
    config[var] = configReader.get("Tracker", var)
    if not config[var]:
      fail("{} is not set".format(var))
  except configparser.NoSectionError as e:
    fail("{}. Does {} exist, is it readable, and is there a [Tracker] section?".format(e, configname))
  except configparser.NoOptionError as e:
    # Only fail if the missing var is NOT a default above
    if var not in config:
      fail(e)

# Try to read timestamp cache, don't worry if can't
# Though this will mean tweeting everyone on the first page
ts = 0
try:
  with open(mydir + "/.lotro_devtracker_ts", "r") as cachefile:
    ts = float(cachefile.read())
except:
  pass

# Get web site
try:
  r = requests.get("{}{}".format(config['baseurl'], "post_tracker.php?tracker=devtracker",
                    timeout=45))
except IOError as e:
  fail(e)
except Exception as e:
  fail(e)

if not str(r.status_code).startswith("20"):
  fail("HTTP {}: {}".format(r.status_code, r.text))

auth = tweepy.OAuthHandler(config['consumer_key'], config['consumer_secret'])
auth.set_access_token(config['access_key'], config['access_secret'])
api = tweepy.API(auth)

# Current HTML of each dev post looks like:
#<div class="trackerbit"><div class="dev-tracker-row">
#  <div class="dev-tracker-span6 threadtitle">
#    <a href="showthread.php?goto=newpost&t=667510"><img src="images/styles/UndergroundStyle/buttons/firstnew.png" border="0" alt="Go to first new post" align="absmiddle"></a>
#    <a href="showthread.php?goto=lastpost&t=667510"><img src="images/styles/UndergroundStyle/buttons/lastpost-right.png" border="0" alt="Go to last post" align="absmiddle"></a>
#    <a href="showthread.php?&postid=7893307#post7893307">U23: Pure War-Steed Cosmetics Have No Category Now And Not Showing Up</a>
#  </div>
#  <div class="dev-tracker-span3 threadstatus">
#    11-21-2018 <span class="time">09:20 AM</span>
#    <br />
#    by SSG_RedPanda
#  </div>
#  <div class="dev-tracker-span3 threadforum">
#    <a href="forumdisplay.php?f=521">LOTRO Store Feedback</a>
#  </div>
#</div>

# Parse the HTML
doc = html.fromstring(r.text)
# Find all divs with class "trackerbit", oldest to newest
for post in reversed(doc.find_class('trackerbit')):
  title = None
  url = None
  forum = None
  by = None
  # Find all links in the one trackerbit
  for element, attribute, link, pos in post.iterlinks():
    if element.tag == "a" and attribute == "href":
      # postid= is the link to the actual post, not an image, new, nor last post
      if "postid" in link:
        url = link
        title = element.text_content()
      # forumdisplay link contains the name of the forum the post is in
      elif "forumdisplay" in link:
        forum = element.text_content()
  # Initialize new timestsmp
  newts = ts
  # find poster and the timestamp of the post from the div with class "threadstatus"
  for byele in post.find_class("threadstatus"):
    # this finds " by " then any characters after it are the poster name
    by = byele.text_content()[ byele.text_content().find(" by ") + 4 : ].rstrip()
    # turns the readable timestamp in to seconds since the epoch
    newts = parser.parse(byele.text_content(), fuzzy=True).timestamp()
  # If we have all the info, and the timestamp is newer than the cached
  # timestamp, tweet
  if title and url and forum and by:
    if newts > ts:
      # Replace @ symbols to avoid mentioning Twitter accounts
      title = title.replace("@","[at]")
      tweet = ""
      # This is a do ... while loop in Python that cuts down the post title until
      # tweet length is less than max tweet length (counts urls fully, currently)
      while True:
        tweet = "#LOTRO dev post by {3} in {0} > \"{1}\" @ {2}".format(forum, title, config['baseurl'] + url, by)
        if len(tweet) < int(config['maxlen']):
          break
        title = title[:-3]
        if len(title) <= 0:
          fail("Tweet too long somehow,\nforum: {}\nurl: {}\nby: {}\n".format(forum, config['baseurl'] + url, by))

      ts = newts
      print("Tweeted: {}".format(tweet))
      try:
        api.update_status(status=tweet)
      except tweepy.error.TweepError as e:
        if e.response.text == 187: #Status is a duplicate.
          pass
        else:
          raise
      time.sleep(0.25)
  else:
    # Info missing .. debug
    fail("Info missing!\nTitle: {}\nURL: {}\nForum: {}\nBy: {}\nTS: {}\nHTML:\n{}\n".format(title, url, forum, by, newts, html.tostring(post)))

# Cache the timestamp of the last tweeted post
try:
  with open(mydir + "/.lotro_devtracker_ts", "w+") as cachefile:
    cachefile.write(str(ts))
except Exception as e:
  fail(e)
