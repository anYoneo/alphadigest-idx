import logging
import time
import requests
import datetime
from pathlib import Path
from rich.table import Table
from typing import List, Dict, Any, Optional

from utils import (
    load_config,
    get_project_root,
    save_json,
    get_today_str,
    setup_logging,
    console
)

logger = logging.getLogger(__name__)

CATEGORIES = {
    "technology_ai": ["ai", "machine learning", "gpt", "openai", "robot", "technology", "software", "app", "tech", "computer", "hardware", "apple", "google", "meta"],
    "science_nature": ["science", "space", "nature", "physics", "biology", "chemistry", "climate", "animal", "discovery", "universe", "nasa"],
    "business_finance": ["business", "finance", "market", "economy", "stock", "crypto", "money", "company", "ceo", "startup", "invest"],
    "storytelling_facts": ["til", "history", "todayilearned", "fact", "story", "human", "odd", "unusual", "weird", "ancient"],
    "trending_viral": ["viral", "trending", "tiktok", "twitter", "drama", "social media", "meme"]
}

def classify_topic(title: str, source: str = "", subreddit: str = "") -> str:
    """Classify a topic based on keywords in title, source, or subreddit."""
    text_to_check = f"{title} {source} {subreddit}".lower()
    
    for category, keywords in CATEGORIES.items():
        if any(keyword in text_to_check for keyword in keywords):
            return category
            
    return "trending_viral"  # Default category

def fetch_google_trends() -> List[Dict[str, Any]]:
    """Fetch trending searches from Google Trends."""
    topics = []
    logger.info("Scanning Google Trends...")
    
    try:
        from pytrends.request import TrendReq
        pytrend = TrendReq(hl='en-US', tz=360)
        
        for region in ['united_states', 'indonesia']:
            logger.info(f"Fetching Google Trends for {region}...")
            trending_df = pytrend.trending_searches(pn=region)
            
            for idx, row in trending_df.iterrows():
                title = row[0]
                topics.append({
                    "title": title,
                    "source": "google_trends",
                    "source_url": f"https://trends.google.com/trends/explore?q={requests.utils.quote(title)}",
                    "score": 1000 - (idx * 10),  # Assign pseudo-score based on rank
                    "category": classify_topic(title, source="google_trends"),
                    "scanned_at": datetime.datetime.now().astimezone().isoformat(),
                    "region": region
                })
            time.sleep(2)  # Avoid rate limiting
    except Exception as e:
        logger.warning(f"Failed to fetch Google Trends: {e}")
        
    return topics

def fetch_reddit(session: requests.Session) -> List[Dict[str, Any]]:
    """Fetch top posts from Reddit using public JSON API."""
    topics = []
    subreddits = ['technology', 'artificial', 'todayilearned', 'science', 'Futurology', 'MachineLearning']
    logger.info(f"Scanning Reddit subreddits: {', '.join(subreddits)}")
    
    headers = {'User-Agent': 'CashFactsDaily-Bot/1.0'}
    
    for sub in subreddits:
        logger.info(f"Fetching /r/{sub}...")
        url = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
        
        try:
            resp = session.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            for child in data.get('data', {}).get('children', []):
                post = child.get('data', {})
                title = post.get('title', '')
                score = post.get('score', 0)
                permalink = post.get('permalink', '')
                
                if score > 100 and title:
                    topics.append({
                        "title": title,
                        "source": "reddit",
                        "source_url": f"https://www.reddit.com{permalink}",
                        "score": score,
                        "category": classify_topic(title, subreddit=sub),
                        "scanned_at": datetime.datetime.now().astimezone().isoformat()
                    })
            time.sleep(1.5)
        except Exception as e:
            logger.warning(f"Failed to fetch Reddit /r/{sub}: {e}")
            
    return topics

def fetch_hackernews(session: requests.Session) -> List[Dict[str, Any]]:
    """Fetch top stories from Hacker News Firebase API."""
    topics = []
    logger.info("Scanning Hacker News...")
    
    try:
        top_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        resp = session.get(top_url, timeout=10)
        resp.raise_for_status()
        story_ids = resp.json()[:30]  # Get top 30 stories
        
        for story_id in story_ids:
            item_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
            item_resp = session.get(item_url, timeout=10)
            item_resp.raise_for_status()
            item = item_resp.json()
            
            if item and item.get('type') == 'story' and not item.get('dead') and not item.get('deleted'):
                score = item.get('score', 0)
                title = item.get('title', '')
                url = item.get('url', f"https://news.ycombinator.com/item?id={story_id}")
                
                if score > 50 and title:
                    topics.append({
                        "title": title,
                        "source": "hackernews",
                        "source_url": url,
                        "score": score,
                        "category": classify_topic(title, source="hackernews"),
                        "scanned_at": datetime.datetime.now().astimezone().isoformat()
                    })
            time.sleep(0.5)
    except Exception as e:
        logger.warning(f"Failed to fetch Hacker News: {e}")
        
    return topics

def deduplicate_topics(topics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove exact duplicates by normalized title."""
    seen = set()
    unique_topics = []
    
    for topic in topics:
        norm_title = topic['title'].strip().lower()
        if norm_title not in seen:
            seen.add(norm_title)
            unique_topics.append(topic)
            
    return unique_topics

def scan_topics() -> Dict[str, Any]:
    """Scan all sources and compile trending topics."""
    logger.info("Starting topic scan...")
    session = requests.Session()
    all_topics = []
    
    # Scan sources
    all_topics.extend(fetch_google_trends())
    all_topics.extend(fetch_reddit(session))
    all_topics.extend(fetch_hackernews(session))
    
    # Process topics
    all_topics = deduplicate_topics(all_topics)
    all_topics.sort(key=lambda x: x['score'], reverse=True)
    
    # Format and add IDs
    formatted_topics = []
    for i, topic in enumerate(all_topics):
        topic_dict = {
            "id": f"topic_{str(i+1).zfill(3)}",
            "title": topic['title'],
            "source": topic['source'],
            "source_url": topic['source_url'],
            "score": topic['score'],
            "category": topic['category'],
            "scanned_at": topic['scanned_at']
        }
        formatted_topics.append(topic_dict)
    
    # Build final result
    timestamp = datetime.datetime.now().astimezone().isoformat()
    result = {
        "scan_date": get_today_str(),
        "scan_timestamp": timestamp,
        "total_topics": len(formatted_topics),
        "sources_scanned": ["google_trends", "reddit", "hackernews"],
        "topics": formatted_topics
    }
    
    # Save to file
    root_dir = get_project_root()
    output_dir = root_dir / "data" / "topics"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / f"topics_{get_today_str()}.json"
    save_json(result, output_file)
    logger.info(f"Saved {len(formatted_topics)} topics to {output_file}")
    
    return result

def print_summary(result: Dict[str, Any]):
    """Print a rich table summary of the scanned topics."""
    table = Table(title=f"Trending Topics Scan ({result['scan_date']})")
    table.add_column("ID", style="cyan")
    table.add_column("Score", style="green", justify="right")
    table.add_column("Category", style="magenta")
    table.add_column("Source", style="yellow")
    table.add_column("Title")
    
    # Print top 15 topics to avoid spamming console
    for topic in result['topics'][:15]:
        table.add_row(
            topic['id'],
            str(topic['score']),
            topic['category'],
            topic['source'],
            topic['title'][:60] + "..." if len(topic['title']) > 60 else topic['title']
        )
        
    console.print(table)
    console.print(f"[bold green]Total topics scanned:[/bold green] {result['total_topics']}")
    console.print(f"[bold blue]Sources successfully queried:[/bold blue] {', '.join(result['sources_scanned'])}")

if __name__ == '__main__':
    results = scan_topics()
    print_summary(results)
