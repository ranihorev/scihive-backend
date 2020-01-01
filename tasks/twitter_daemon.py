"""
Periodically checks Twitter for tweets about arxiv papers we recognize
and logs the tweets into mongodb database "arxiv", under "tweets" collection.
"""
import json
import logging
import os
import re
from collections import defaultdict
from time import sleep

import pytz
import math
import datetime

import tweepy
import pymongo

from .utils import catch_exceptions

from dotenv import load_dotenv
load_dotenv()

# settings
# -----------------------------------------------------------------------------
sleep_time = 60*15 # in seconds, between twitter API calls. Default rate limit is 180 per 15 minutes
max_tweet_records = 15

logger = logging.getLogger(__name__)

USERS_FILENAME = 'twitter_users.json'
# convenience functions
# -----------------------------------------------------------------------------


def get_api_connector():
    key = os.environ.get('TWITTER_KEY')
    secret = os.environ.get('TWITTER_SECRET')
    auth = tweepy.AppAuthHandler(key, secret)
    return tweepy.API(auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True)


def extract_arxiv_pids(r):
    pids = []
    for u in r.entities['urls']:
        m = re.search('arxiv.org/abs/([0-9]+\.[0-9]+)', u['expanded_url'])
        if m:
            rawid = m.group(1)
            pids.append(rawid)
    return pids


def get_latest_or_loop(q):
    results = None
    while results is None:
        try:
            results = api.search(q=q, count=100, result_type="mixed", tweet_mode='extended')
        except Exception as e:
            logger.info('there was some problem (waiting some time and trying again):')
            logger.error(e)

    logger.info('Fetched results')
    return results


epochd = datetime.datetime(1970,1,1,tzinfo=pytz.utc) # time of epoch


def get_age_decay(age):
    """
    Calc Gauss decay factor - based on elastic search decay function
    :param age: age in hours
    :return: decay factor
    """
    SCALE = 7  # The distance from origin at which the computed factor will equal decay parameter
    DECAY = 0.5  # Defines the score at scale compared to zero (better to update only the scale and keep it fixed
    OFFSET = 2  # the decay function will only compute the decay function for post with a distance greater
    TIME_FACTOR = 0.75  # Reduce the decay over time by taking the TIME FACTOR power of the time value

    if age <= OFFSET:
        return 1
    gamma = math.log(DECAY) / SCALE
    return math.exp(gamma * (age ** TIME_FACTOR))


def calc_papers_twitter_score(papers_to_update):
    papers_to_update = list(set(papers_to_update))
    papers_tweets = list(db_tweets.find({'pids': {'$in': papers_to_update}}))
    score_per_paper = defaultdict(int)
    simple_score_per_paper = defaultdict(int)
    links_per_paper = defaultdict(list)
    for t in papers_tweets:
        followers_score = max(math.log10(t['user_followers_count'] + 1), 1)
        tot_score = (t['likes'] + 2 * t['retweets']) * (t.get('replies', 0) * 4 + 0.5) / followers_score
        simple_score = t['likes'] + 2 * t['retweets'] + 4 * t.get('replies', 0)

        for cur_p in t['pids']:
            simple_score_per_paper[cur_p] += simple_score
            score_per_paper[cur_p] += tot_score
            links_per_paper[cur_p].append({'tname': t['user_screen_name'], 'tid': t['_id'], 'rt': t['retweets'],
                                           'name': t.get('user_name', t['user_screen_name']), 'likes': t['likes'],
                                           'replies': t.get('replies', 0)})
    return simple_score_per_paper, score_per_paper, links_per_paper


def summarize_tweets(papers_to_update):
    simple_score_per_paper, score_per_paper, links_per_paper = calc_papers_twitter_score(papers_to_update)
    all_papers = list(db_papers.find({'_id': {'$in': papers_to_update}}))
    for cur_p in all_papers:
        logger.info(f'Updating paper {cur_p["_id"]}')
        twitter_score = score_per_paper.get(cur_p['_id'], 0)
        if twitter_score > 0:
            data = {'twtr_score': twitter_score, 'twtr_sum': simple_score_per_paper.get(cur_p['_id'], 0)}
            if cur_p['_id'] in links_per_paper:
                data['twtr_links'] = links_per_paper[cur_p['_id']]
            db_papers.update({'_id': cur_p['_id']}, {'$set': data}, True)


def fetch_twitter_users(usernames):
    logger.info('Fetching tweets from users list')
    tweets = []
    for idx, u in enumerate(usernames):
        try:
            tweets += api.user_timeline(screen_name=u['screen_name'], count=100, tweet_mode='extended')
            # if idx > 3:
            #     break
        except Exception as e:
            logger.warning(f'Failed to fetch tweets from {u["screen_name"]}')
        sleep(1)
    logger.info('Finished fetching tweets from users list')
    return tweets


def fetch_tweets():
    logger.info('Fetching tweets')
    # fetch the latest mentioning arxiv.org
    results = get_latest_or_loop('arxiv.org')

    if os.path.isfile(USERS_FILENAME):
        usernames = json.load(open(USERS_FILENAME, 'r'))
        results += fetch_twitter_users(usernames)
    else:
        logger.warning('Users file is missing')
    return results


def tweet_to_dict(r, arxiv_pids, dnow_utc, num_replies):
    d = r.created_at.replace(tzinfo=pytz.UTC)  # datetime instance
    tweet = {}
    tweet['_id'] = r.id_str
    tweet['pids'] = arxiv_pids  # arxiv paper ids mentioned in this tweet
    tweet['inserted_at_date'] = dnow_utc
    tweet['created_at_date'] = d
    tweet['created_at_time'] = (d - epochd).total_seconds()  # seconds since epoch
    tweet['lang'] = r.lang
    tweet['text'] = r.full_text
    tweet['retweets'] = r.retweet_count
    tweet['likes'] = r.favorite_count
    tweet['replies'] = num_replies
    tweet['user_screen_name'] = r.author.screen_name
    tweet['user_name'] = r.author.name
    tweet['user_followers_count'] = r.author.followers_count
    tweet['user_following_count'] = r.author.friends_count
    return tweet


def is_tweet_new(tweet_id_q):
    if db_tweets.find_one(tweet_id_q):
        is_new = False
    else:
        is_new = True
    return is_new

def find_num_replies(t):
    try:
        replies = api.search(q=f'to:{t.author.screen_name}', since_id=t.id_str, count=100)
        filter_func = lambda x: x.in_reply_to_status_id_str == t.id_str and x.author.screen_name != t.author.screen_name
        rel_replies = list(filter(filter_func, replies))
        return len(rel_replies)
    except Exception as e:
        logger.error(f'Failed to fetch replies for tweet - {t.id_str} - {e}')
        return 0


def get_pids_in_db(arxiv_pids):
    papers_in_db = list(db_papers.find({'_id': {'$in': arxiv_pids}}, {'_id': 1}))
    return [x['_id'] for x in papers_in_db]


def process_tweets(tweets_raw_data):
    logger.info('Process tweets')
    dnow_utc = datetime.datetime.now(datetime.timezone.utc)
    num_new = 0
    papers_to_update = []
    unique_tweet_ids = set()

    for r in tweets_raw_data:
        if hasattr(r, 'retweeted_status'):
            # logger.info('Tweet is a retweet')
            r = r.retweeted_status

        if r.id_str in unique_tweet_ids: continue

        arxiv_pids = extract_arxiv_pids(r)
        if not arxiv_pids : continue
        arxiv_pids = get_pids_in_db(arxiv_pids)
        if not arxiv_pids:
            logger.info(f'Arxiv pids are not in DB - tweet {r.id_str}')
            continue

        papers_to_update += arxiv_pids

        num_replies = find_num_replies(r)
        tweet = tweet_to_dict(r, arxiv_pids, dnow_utc, num_replies)

        tweet_id_q = {'_id': r.id_str}

        db_tweets.update(tweet_id_q, {'$set': tweet}, True)

        unique_tweet_ids.add(r.id_str)
        logger.info(f'Found tweet for {arxiv_pids} with {tweet["likes"]} likes')

    logger.info(f'processed {len(tweets_raw_data)} new tweets')
    return papers_to_update


@catch_exceptions(logger=logger)
def main_twitter_fetcher():
    tweets = fetch_tweets()
    papers_to_update = process_tweets(tweets)
    summarize_tweets(papers_to_update)


@catch_exceptions(logger=logger)
def recalculate():
    all_papers = list(db_papers.find({}, {'_id': 1}))
    summarize_tweets([p['_id'] for p in all_papers])

# -----------------------------------------------------------------------------

# authenticate to twitter API

api = get_api_connector()

# connect to mongodb instance
client = pymongo.MongoClient()
mdb = client.arxiv
db_tweets = mdb.tweets # the "tweets" collection in "arxiv" database
db_papers = mdb.papers

# main loop
if __name__ == '__main__':
    from logger import logger_config
    logger_config(info_filename='twitter_daemon.log')
    main_twitter_fetcher()
