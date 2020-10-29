"""
Periodically checks Twitter for tweets about arxiv papers we recognize
and logs the tweets into database "arxiv", under "tweets" collection.
"""
import datetime
import json
import logging
import math
import os
import re
from time import sleep

import pytz
import tweepy
from sqlalchemy import func
from ..models import Paper, Tweet, db
from .utils import catch_exceptions

# settings
# -----------------------------------------------------------------------------
sleep_time = 60 * 15  # in seconds, between twitter API calls. Default rate limit is 180 per 15 minutes
max_tweet_records = 15

logger = logging.getLogger(__name__)

USERS_FILENAME = 'src/twitter_users.json'
# convenience functions
# -----------------------------------------------------------------------------


def get_api_connector():
    key = os.environ.get('TWITTER_KEY')
    secret = os.environ.get('TWITTER_SECRET')
    if not key or not secret:
        return None
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


def get_latest_or_loop(api, q):
    results = None
    while results is None:
        try:
            results = api.search(q=q, count=100, result_type="mixed", tweet_mode='extended')
        except Exception as e:
            logger.info('there was some problem (waiting some time and trying again):')
            logger.error(e)

    logger.info('Fetched results')
    return results


epochd = datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)  # time of epoch


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


def summarize_tweets(papers_to_update):
    papers_to_update = list(set(papers_to_update))
    papers_tweets = a = db.session.query(Paper).join(Tweet).with_entities(Paper, func.sum(Tweet.likes + 2 * Tweet.retweets +
                                                                                          4 * Tweet.replies)).filter(Paper.id.in_(papers_to_update)).group_by(Paper.id).all()
    for paper, score in papers_tweets:
        paper.twitter_score = score

    db.session.commit()


def fetch_twitter_users(api, usernames):
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


def fetch_tweets(api):
    logger.info('Fetching tweets')
    # fetch the latest mentioning arxiv.org
    results = get_latest_or_loop(api, 'arxiv.org')

    if os.path.isfile(USERS_FILENAME):
        usernames = json.load(open(USERS_FILENAME, 'r'))
        # results += fetch_twitter_users(api, usernames)
    else:
        logger.warning('Users file is missing')
    return results


def create_tweet(r, paper, dnow_utc, num_replies):
    creation_date = r.created_at.replace(tzinfo=pytz.UTC)
    tweet = Tweet(id=r.id_str, paper=paper, insertion_date=dnow_utc, creation_date=creation_date, lang=r.lang, text=r.full_text, retweets=r.retweet_count, likes=r.favorite_count,
                  replies=num_replies, user_screen_name=r.author.screen_name, user_name=r.author.name, user_followers_count=r.author.followers_count, user_following_count=r.author.friends_count)
    db.session.merge(tweet)
    db.session.commit()
    return tweet


def find_num_replies(api, t):
    try:
        replies = api.search(q=f'to:{t.author.screen_name}', since_id=t.id_str, count=100)
        def filter_func(x): return x.in_reply_to_status_id_str == t.id_str and x.author.screen_name != t.author.screen_name
        rel_replies = list(filter(filter_func, replies))
        return len(rel_replies)
    except Exception as e:
        logger.error(f'Failed to fetch replies for tweet - {t.id_str} - {e}')
        return 0


def process_tweets(api, tweets_raw_data):
    logger.info('Process tweets')
    dnow_utc = datetime.datetime.now(datetime.timezone.utc)
    num_new = 0
    papers_to_update = []
    unique_tweet_ids = set()

    for r in tweets_raw_data:
        if hasattr(r, 'retweeted_status'):
            # logger.info('Tweet is a retweet')
            r = r.retweeted_status

        if r.id_str in unique_tweet_ids:
            continue

        arxiv_pids = extract_arxiv_pids(r)
        if not arxiv_pids:
            continue

        paper = Paper.query.filter(Paper.original_id.in_(arxiv_pids)).first()
        if not paper:
            logger.info(f'No Arxiv pid found in DB - tweet {r.id_str}')
            continue

        papers_to_update.append(paper.id)

        num_replies = find_num_replies(api, r)
        tweet = create_tweet(r, paper, dnow_utc, num_replies)

        unique_tweet_ids.add(r.id_str)
        logger.info(f'Found tweet for {paper.id} with {tweet.likes} likes')

    logger.info(f'processed {len(tweets_raw_data)} new tweets')
    return papers_to_update


@catch_exceptions(logger=logger)
def main_twitter_fetcher():
    api = get_api_connector()
    if not api:
        logger.error('Twitter API keys are missing. Skipping')
        return
    tweets = fetch_tweets(api)
    papers_to_update = process_tweets(api, tweets)
    summarize_tweets(papers_to_update)
