"""
Web Scraping Module for Enhanced Chatbot Context
Scrapes educational content from Wikipedia, Khan Academy, and other sources
Extracts relevant text, images, and reference links
"""
import requests
from bs4 import BeautifulSoup
import re
import logging
from urllib.parse import urljoin, quote
import hashlib
from typing import Dict, List, Optional

logger = logging.getLogger('students')

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'


def normalize_query(query: str) -> str:
    """Normalize query for searching"""
    # Remove special characters, convert to lowercase
    normalized = re.sub(r'[^\w\s]', ' ', query.lower())
    normalized = ' '.join(normalized.split())
    return normalized


def scrape_wikipedia(query: str, max_paragraphs: int = 3) -> Dict:
    """
    Scrape Wikipedia for educational content
    Returns summary, images, and reference link
    """
    result = {
        'source': 'Wikipedia',
        'url': None,
        'content': '',
        'images': [],
        'success': False
    }
    
    try:
        # Search Wikipedia
        search_url = f"https://en.wikipedia.org/w/api.php"
        params = {
            'action': 'query',
            'list': 'search',
            'srsearch': query,
            'format': 'json',
            'utf8': 1
        }
        
        response = requests.get(search_url, params=params, timeout=10, headers={'User-Agent': USER_AGENT})
        response.raise_for_status()
        data = response.json()
        
        if not data.get('query', {}).get('search'):
            logger.info(f"No Wikipedia results for: {query}")
            return result
        
        # Get first result's page ID
        page_title = data['query']['search'][0]['title']
        
        # Get page content
        content_url = f"https://en.wikipedia.org/w/api.php"
        params = {
            'action': 'query',
            'prop': 'extracts|pageimages',
            'exintro': True,
            'explaintext': True,
            'piprop': 'original',
            'titles': page_title,
            'format': 'json',
            'utf8': 1
        }
        
        response = requests.get(content_url, params=params, timeout=10, headers={'User-Agent': USER_AGENT})
        response.raise_for_status()
        data = response.json()
        
        pages = data.get('query', {}).get('pages', {})
        if pages:
            page_data = list(pages.values())[0]
            
            # Extract content
            extract = page_data.get('extract', '')
            if extract:
                # Limit to first few paragraphs
                paragraphs = extract.split('\n\n')[:max_paragraphs]
                result['content'] = '\n\n'.join(paragraphs)
            
            # Extract main image
            if 'original' in page_data:
                result['images'].append({
                    'url': page_data['original']['source'],
                    'type': 'wikipedia_main'
                })
            
            # Build article URL
            result['url'] = f"https://en.wikipedia.org/wiki/{quote(page_title.replace(' ', '_'))}"
            result['success'] = True
            
            logger.info(f"✅ Scraped Wikipedia: {page_title}")
        
    except Exception as e:
        logger.error(f"Wikipedia scraping error: {str(e)}")
    
    return result


def scrape_khan_academy(query: str) -> Dict:
    """
    Scrape Khan Academy for educational content
    Note: Khan Academy has strict anti-scraping measures
    This is a basic implementation
    """
    result = {
        'source': 'Khan Academy',
        'url': None,
        'content': '',
        'images': [],
        'success': False
    }
    
    try:
        # Search Khan Academy
        search_query = quote(query)
        search_url = f"https://www.khanacademy.org/search?page_search_query={search_query}"
        
        response = requests.get(search_url, timeout=10, headers={'User-Agent': USER_AGENT})
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find first article link (this may need adjustment based on their current HTML structure)
        article_link = soup.find('a', href=re.compile(r'/[a-z\-]+/[a-z\-]+'))
        
        if article_link and article_link.get('href'):
            article_url = urljoin('https://www.khanacademy.org', article_link['href'])
            result['url'] = article_url
            
            # Get article page
            article_response = requests.get(article_url, timeout=10, headers={'User-Agent': USER_AGENT})
            article_response.raise_for_status()
            
            article_soup = BeautifulSoup(article_response.text, 'html.parser')
            
            # Extract paragraphs (adjust selectors as needed)
            paragraphs = article_soup.find_all('p', limit=3)
            result['content'] = '\n\n'.join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
            
            # Extract images
            images = article_soup.find_all('img', src=True, limit=2)
            for img in images:
                img_url = urljoin(article_url, img['src'])
                if img_url and not img_url.endswith('.svg'):  # Skip SVG logos
                    result['images'].append({
                        'url': img_url,
                        'type': 'khan_academy'
                    })
            
            result['success'] = True
            logger.info(f"✅ Scraped Khan Academy: {article_url}")
        
    except Exception as e:
        logger.error(f"Khan Academy scraping error: {str(e)}")
    
    return result


def scrape_ncert_official(query: str, standard: str = None) -> Dict:
    """
    Scrape NCERT official website for educational content
    """
    result = {
        'source': 'NCERT Official',
        'url': None,
        'content': '',
        'images': [],
        'success': False
    }
    
    try:
        # NCERT website structure may vary
        # This is a placeholder implementation
        base_url = "https://ncert.nic.in/"
        
        # For now, just return the base URL as reference
        result['url'] = base_url
        result['content'] = f"For official NCERT content on '{query}', please refer to NCERT textbooks and materials."
        
        logger.info(f"NCERT reference added for: {query}")
        
    except Exception as e:
        logger.error(f"NCERT scraping error: {str(e)}")
    
    return result


def search_educational_images(query: str, max_images: int = 3) -> List[Dict]:
    """
    Search for educational images related to the query
    Uses Wikipedia and other open educational resources
    """
    images = []
    
    try:
        # Get images from Wikipedia
        wiki_result = scrape_wikipedia(query, max_paragraphs=1)
        if wiki_result['images']:
            images.extend(wiki_result['images'])
        
        # Can add more image sources here (Wikimedia Commons, etc.)
        
        return images[:max_images]
        
    except Exception as e:
        logger.error(f"Image search error: {str(e)}")
        return []


def scrape_multiple_sources(query: str, include_images: bool = True) -> Dict:
    """
    Scrape multiple sources and combine results
    Returns combined content, images, and references
    """
    combined = {
        'content': '',
        'images': [],
        'sources': [],
        'success': False
    }
    
    # Scrape Wikipedia (most reliable)
    wiki_result = scrape_wikipedia(query)
    if wiki_result['success']:
        combined['content'] += f"\n\n**From Wikipedia:**\n{wiki_result['content']}"
        if include_images and wiki_result['images']:
            combined['images'].extend(wiki_result['images'])
        combined['sources'].append({
            'name': wiki_result['source'],
            'url': wiki_result['url']
        })
        combined['success'] = True
    
    # Try Khan Academy (may be blocked)
    khan_result = scrape_khan_academy(query)
    if khan_result['success']:
        combined['content'] += f"\n\n**From Khan Academy:**\n{khan_result['content']}"
        if include_images and khan_result['images']:
            combined['images'].extend(khan_result['images'])
        combined['sources'].append({
            'name': khan_result['source'],
            'url': khan_result['url']
        })
    
    # Add NCERT reference
    ncert_result = scrape_ncert_official(query)
    if ncert_result['url']:
        combined['sources'].append({
            'name': ncert_result['source'],
            'url': ncert_result['url']
        })
    
    # Limit images
    combined['images'] = combined['images'][:3]
    
    logger.info(f"Scraped {len(combined['sources'])} sources, found {len(combined['images'])} images")
    
    return combined


def is_educational_query(query: str) -> bool:
    """
    Determine if query is educational/subject-oriented
    Returns True if query needs RAG + web scraping
    """
    # Simple queries that don't need scraping
    simple_patterns = [
        r'^(hi|hello|hey|good morning|good evening)',
        r'^(bye|goodbye|see you)',
        r'^(thank you|thanks|thank u)',
        r'^(how are you|what\'s up)',
        r'^(yes|no|ok|okay)',
    ]
    
    query_lower = query.lower().strip()
    
    for pattern in simple_patterns:
        if re.match(pattern, query_lower):
            return False
    
    # Educational keywords
    educational_keywords = [
        'what', 'how', 'why', 'explain', 'define', 'describe',
        'calculate', 'solve', 'prove', 'difference between',
        'meaning of', 'example of', 'diagram', 'process',
        'photosynthesis', 'mathematics', 'science', 'history',
        'geography', 'physics', 'chemistry', 'biology'
    ]
    
    return any(keyword in query_lower for keyword in educational_keywords)


def get_query_hash(query: str) -> str:
    """Generate MD5 hash of normalized query for caching"""
    normalized = normalize_query(query)
    return hashlib.md5(normalized.encode()).hexdigest()
