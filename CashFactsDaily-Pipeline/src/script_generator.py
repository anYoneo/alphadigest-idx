import logging
import os
import time
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from openai import OpenAI
from rich.progress import Progress
from rich.table import Table

from utils import (
    load_config,
    load_env,
    get_project_root,
    save_json,
    load_json,
    get_today_str,
    setup_logging,
    console
)

logger = logging.getLogger(__name__)

NEWSJACKING_PROMPT = """You are a viral short-form video scriptwriter for {brand_name} ({handle}).
Write a 45-60 second spoken script about this trending topic:

TOPIC: {topic_title}
SOURCE: {source_url}

Format:
## HOOK (0-3 seconds)
[One shocking/curiosity-gap opening line that stops scrolling]

## SETUP (3-12 seconds) 
[Context that makes the hook even more intriguing]

## VALUE (12-45 seconds)
[3-4 key facts/insights, each on a new line with [B-Roll: description] visual cues]

## CLIMAX (45-55 seconds)
[The surprising conclusion or "so what" takeaway]

## CTA (55-60 seconds)
"{cta}"

Rules:
- Tone: {tone}
- Language: {language}
- Target: {target_audience}
- Use spoken language, NOT written essay style
- Include *emphasis markers* for important words
- Add [B-Roll: description] cues for visual changes
- Start with a HOOK that creates a curiosity gap
- NEVER start with "In today's fast-paced world" or similar AI clichés
- Keep word count between 120-180 words"""

STORYTELLING_PROMPT = """You are a master storyteller for {brand_name} ({handle}).
Write a 60-90 second narrative script about this fascinating topic:

TOPIC: {topic_title}

Format:
## HOOK (0-3 seconds)
[One mind-blowing fact or question that seems impossible]

## TENSION (3-15 seconds)
[Build the mystery — what happened? why does this matter?]

## STORY (15-55 seconds)
[Tell the story in 4-5 beats, each with [B-Roll: description] visual cues]
[Use vivid details, names, dates, numbers]

## TWIST (55-70 seconds)
[The unexpected conclusion that changes everything]

## CTA (70-80 seconds)
"{cta}"

Rules:
- Tone: {tone}
- Language: {language}
- Use the Problem → Agitation → Climax → Resolution structure
- Include *emphasis markers* for dramatic moments
- Add [B-Roll: description] cues every 3-5 seconds
- NEVER use passive voice
- Keep word count between 150-220 words"""

EDUCATION_PROMPT = """You are an engaging educator for {brand_name} ({handle}).
Write a 45-60 second tutorial/tips script about:

TOPIC: {topic_title}

Format:
## HOOK (0-3 seconds)
[A bold claim or surprising statistic that makes people save this video]

## LIST/STEPS (3-50 seconds)
[3-5 actionable tips/steps, each formatted as:]
Tip 1: [Title]
[Brief explanation + [B-Roll: description]]

## SUMMARY (50-55 seconds)
[One-line recap of the key takeaway]

## CTA (55-60 seconds)
"Save this for later. {cta}"

Rules:
- Tone: {tone}
- Language: {language}
- Make it "save-worthy" — practical, actionable value
- Use numbered tips for clarity
- Include *emphasis markers*
- Add [B-Roll: description] cues
- Keep word count between 120-180 words"""

AUTHORITY_PROMPT = """You are a trusted expert for {brand_name} ({handle}).
Write a 45-60 second comparison/review script about:

TOPIC: {topic_title}

Format:
## HOOK (0-3 seconds)
[A provocative ranking statement or "X vs Y" comparison]

## BREAKDOWN (3-45 seconds)
[Compare/rank items with clear criteria, each with [B-Roll: description]]

## VERDICT (45-55 seconds)
[Your definitive recommendation]

## CTA (55-60 seconds)
"Comment [KEYWORD] and I'll send you the full comparison. {cta}"

Rules:
- Tone: {tone}
- Language: {language}
- Be opinionated — don't sit on the fence
- Include specific numbers, prices, or metrics
- Add [B-Roll: description] cues
- Keep word count between 120-180 words"""

PROMPTS = {
    "newsjacking": NEWSJACKING_PROMPT,
    "storytelling": STORYTELLING_PROMPT,
    "education": EDUCATION_PROMPT,
    "authority": AUTHORITY_PROMPT,
}


def select_topics(topics_data: List[Dict[str, Any]], n: int = 4) -> List[Dict[str, Any]]:
    """
    Selects top N topics based on score and attempts to maintain category diversity.
    
    Args:
        topics_data: List of topic dictionaries.
        n: Number of topics to select.
        
    Returns:
        List of selected topic dictionaries.
    """
    if not topics_data:
        return []
        
    sorted_topics = sorted(topics_data, key=lambda x: x.get('score', 0), reverse=True)
    selected = []
    seen_categories = set()
    
    # First pass: try to get unique categories
    for topic in sorted_topics:
        category = topic.get('category', '')
        if category not in seen_categories:
            selected.append(topic)
            seen_categories.add(category)
        if len(selected) == n:
            break
            
    # Second pass: if we need more, just pick highest scoring ones we missed
    if len(selected) < n:
        for topic in sorted_topics:
            if topic not in selected:
                selected.append(topic)
            if len(selected) == n:
                break
                
    return selected


def determine_pillar(topic: Dict[str, Any]) -> str:
    """
    Determines the best content pillar for a given topic based on category and title keywords.
    
    Args:
        topic: The topic dictionary.
        
    Returns:
        The content pillar as a string.
    """
    category = topic.get('category', '').lower()
    title = topic.get('title', '').lower()
    
    # Keyword based matching for specific pillars
    if any(keyword in title for keyword in ['how', 'tips', 'guide', 'tools']):
        return 'education'
    if any(keyword in title for keyword in ['vs', 'best', 'review', 'compare']):
        return 'authority'
        
    # Category based matching
    if category in ['trending_viral', 'technology_ai']:
        # Could also check recency here if available in topic data
        return 'newsjacking'
    if category in ['science_nature', 'storytelling_facts']:
        return 'storytelling'
        
    # Default fallback
    return 'newsjacking'


def build_prompt(topic: Dict[str, Any], pillar: str, brand_config: Dict[str, Any], language: str) -> str:
    """
    Builds the full prompt for the LLM based on the topic, pillar, and brand config.
    
    Args:
        topic: The topic dictionary.
        pillar: The selected content pillar.
        brand_config: Dictionary containing brand settings.
        language: Target language ('en' or 'id').
        
    Returns:
        Formatted prompt string.
    """
    template = PROMPTS.get(pillar, NEWSJACKING_PROMPT)
    lang_str = "English" if language.lower() == "en" else "Indonesian"
    
    return template.format(
        brand_name=brand_config.get('name', 'CashFactsDaily'),
        handle=brand_config.get('handle', '@CashFactsDaily'),
        topic_title=topic.get('title', 'Unknown Topic'),
        source_url=topic.get('source_url', 'N/A'),
        tone=brand_config.get('tone', 'Engaging and fast-paced'),
        language=lang_str,
        target_audience=brand_config.get('target_audience', 'General audience'),
        cta=brand_config.get('cta', 'Follow for more!')
    )


def generate_script(prompt: str, config: Dict[str, Any]) -> Optional[str]:
    """
    Calls the DeepSeek API to generate a script based on the prompt.
    
    Args:
        prompt: The fully formatted prompt.
        config: The global configuration dictionary containing LLM settings.
        
    Returns:
        The generated script text, or None if generation failed.
    """
    load_env()
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        logger.error("DEEPSEEK_API_KEY environment variable is missing.")
        return None
        
    llm_config = config.get('llm', {})
    base_url = llm_config.get('base_url', 'https://api.deepseek.com/v1')
    model = llm_config.get('model', 'deepseek-chat')
    temperature = llm_config.get('temperature', 0.7)
    max_tokens = llm_config.get('max_tokens', 1000)
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    system_prompt = "You are a professional short-form video scriptwriter."
    
    retries = 1
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error calling LLM API (Attempt {attempt + 1}/{retries + 1}): {e}")
            if attempt < retries:
                logger.info("Retrying in 2 seconds...")
                time.sleep(2)
                
    return None


def save_script(script_text: str, metadata: Dict[str, Any], config: Dict[str, Any], filename: str) -> None:
    """
    Saves the generated script as a markdown file with YAML frontmatter.
    
    Args:
        script_text: The generated script content.
        metadata: Dictionary containing metadata for the frontmatter.
        config: The global configuration dictionary.
        filename: The name of the file to save.
    """
    root = get_project_root()
    pending_dir = root / 'scripts' / 'pending'
    pending_dir.mkdir(parents=True, exist_ok=True)
    filepath = pending_dir / filename
    
    word_count = len(script_text.split())
    # Estimate duration: average 3 words per second spoken
    estimated_duration_seconds = word_count // 3
    
    now_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).strftime("%Y-%m-%dT%H:%M:%S+07:00")
    
    # Escape quotes in title
    safe_topic = str(metadata.get('topic', '')).replace('"', "'")
    
    frontmatter = f"""---
topic: "{safe_topic}"
pillar: {metadata.get('pillar', 'newsjacking')}
language: {metadata.get('language', 'en')}
brand: {metadata.get('brand', 'CashFactsDaily')}
generated_at: "{now_str}"
source: {metadata.get('source', 'unknown')}
source_url: "{metadata.get('source_url', '')}"
word_count: {word_count}
estimated_duration_seconds: {estimated_duration_seconds}
---

"""
    full_content = frontmatter + script_text
    filepath.write_text(full_content, encoding='utf-8')
    logger.info(f"Successfully saved script to {filepath}")


def generate_all_scripts(topics_file: Optional[str] = None, n: int = 4) -> None:
    """
    Main pipeline function to load topics, generate scripts, and save them.
    
    Args:
        topics_file: Optional path to a specific topics JSON file.
        n: Number of topics to generate scripts for.
    """
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return
        
    brands_config = config.get('brands', {})
    brand_en = brands_config.get('en', {})
    brand_id = brands_config.get('id', {})
    root = get_project_root()
    today = get_today_str()
    
    if not topics_file:
        topics_file = str(root / 'data' / 'topics' / f'topics_{today}.json')
        
    if not os.path.exists(topics_file):
        logger.error(f"Topics file not found: {topics_file}")
        return
        
    try:
        topics_data = load_json(topics_file)
    except Exception as e:
        logger.error(f"Failed to parse topics JSON: {e}")
        return
        
    if isinstance(topics_data, dict):
        topics_list = topics_data.get('topics', [])
    else:
        topics_list = topics_data
        
    if not topics_list:
        logger.warning("No topics found in the specified file.")
        return
        
    selected_topics = select_topics(topics_list, n=n)
    logger.info(f"Selected {len(selected_topics)} topics for generation.")
    
    summary_data = []
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Generating scripts...", total=len(selected_topics) * 2)
        
        for idx, topic in enumerate(selected_topics):
            pillar = determine_pillar(topic)
            
            for lang in ['en', 'id']:
                brand_config = brand_en if lang == 'en' else brand_id
                prompt = build_prompt(topic, pillar, brand_config, lang)
                script_text = generate_script(prompt, config)
                
                if script_text:
                    filename = f"{today}_{pillar}_{lang}_{idx+1:03d}.md"
                    metadata = {
                        'topic': topic.get('title', 'Unknown Topic'),
                        'pillar': pillar,
                        'language': lang,
                        'brand': brand_config.get('name', 'CashFactsDaily' if lang == 'en' else 'FaktaCuan'),
                        'source': topic.get('source', 'unknown'),
                        'source_url': topic.get('source_url', '')
                    }
                    save_script(script_text, metadata, config, filename)
                    summary_data.append((metadata['topic'][:40] + "...", pillar, lang, "Success", filename))
                else:
                    summary_data.append((topic.get('title', 'Unknown Topic')[:40] + "...", pillar, lang, "Failed", "-"))
                
                progress.advance(task)
                # Rate limit between API calls
                time.sleep(2)
                
    # Display summary
    table = Table(title=f"Script Generation Summary ({today})")
    table.add_column("Topic", style="cyan")
    table.add_column("Pillar", style="magenta")
    table.add_column("Lang", style="green")
    table.add_column("Status", style="bold")
    table.add_column("Filename", style="blue")
    
    for row in summary_data:
        status_color = "green" if row[3] == "Success" else "red"
        table.add_row(row[0], row[1], row[2], f"[{status_color}]{row[3]}[/{status_color}]", row[4])
        
    console.print(table)


if __name__ == '__main__':
    logger.info("Starting Script Generator Pipeline")
    generate_all_scripts(n=4)
    logger.info("Script Generator Pipeline Completed")
