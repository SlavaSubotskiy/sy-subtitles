"""Download materials from amruta.org and set up talk directory.

Fetches SRT subtitles, transcript text, and extracts Vimeo video URLs
from amruta.org talk pages using WordPress session cookie authentication.
Supports multiple videos per page and batch processing.

Usage:
    # Single talk (date/slug auto-extracted from URL):
    python -m tools.download --url URL [--what srt,text] [--cookie COOKIE]

    # Batch mode:
    python -m tools.download --manifest queue.yaml [--what srt,text] [--cookie COOKIE]
"""

import argparse
import glob as globmod
import os
import re
import subprocess

import requests
import yaml
from bs4 import BeautifulSoup, Tag
from dotenv import load_dotenv


def parse_amruta_url(url):
    """Extract date and slug from amruta.org URL.

    URL pattern: https://www.amruta.org/YYYY/MM/DD/slug/
    Strips trailing year/location suffixes that duplicate the date prefix.
    Title-cases the slug: ganesha-puja → Ganesha-Puja.
    Returns (date, slug) tuple. Raises ValueError if URL doesn't match.
    """
    match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/([^/?#]+)', url)
    if not match:
        raise ValueError(f"Cannot parse date/slug from URL: {url}")
    year, month, day, raw_slug = match.groups()
    raw_slug = raw_slug.rstrip('/')
    date = f"{year}-{month}-{day}"
    # Strip trailing year (e.g. "ganesha-puja-cabella-1993" → "ganesha-puja-cabella")
    raw_slug = re.sub(r'-\d{4}$', '', raw_slug)
    # Title-case: ganesha-puja-cabella → Ganesha-Puja-Cabella
    slug = '-'.join(part.capitalize() for part in raw_slug.split('-'))
    return date, slug


def slugify_video_name(name):
    """Slugify a video label for use as directory name.

    Keeps capitalization, spaces → hyphens, strips special chars.
    """
    name = name.strip()
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '-', name)
    name = re.sub(r'-+', '-', name)
    return name.strip('-')


class AmrutaDownloader:
    """Downloads materials from amruta.org talk pages."""

    def __init__(self, session_cookie=None):
        load_dotenv()
        self.session_cookie = session_cookie or os.environ.get('AMRUTA_SESSION_COOKIE', '')
        self.session = requests.Session()
        self.session.headers['User-Agent'] = (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        )
        if self.session_cookie:
            for part in self.session_cookie.split('; '):
                if '=' in part:
                    name, value = part.split('=', 1)
                    self.session.cookies.set(name, value, domain='.amruta.org')

    def fetch_talk_page(self, url):
        """Fetch and parse a talk page."""
        resp = self.session.get(url)
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code} for {url}")
            print(f"  Response body (first 500 chars): {resp.text[:500]}")
            resp.raise_for_status()
        return BeautifulSoup(resp.text, 'html.parser')

    def extract_title(self, soup):
        """Extract talk title from page."""
        title_tag = soup.find('h1', class_='entry-title')
        if title_tag:
            return title_tag.get_text(strip=True)
        title_tag = soup.find('title')
        if title_tag:
            text = title_tag.get_text(strip=True)
            # Remove site suffix like " – Nirmala Vidya Amruta"
            return re.sub(r'\s*[–—|]\s*Nirmala.*$', '', text)
        return None

    def extract_video_labels(self, soup):
        """Extract video labels and Vimeo URLs from page.

        Looks for amruta.org's embedded-video-wrapper structure first,
        then falls back to searching preceding text/headings.
        Returns list of {title, slug, vimeo_url} dicts.
        """
        videos = []

        # Strategy 1: amruta.org embedded-video-wrapper structure
        wrappers = soup.find_all('div', class_='embedded-video-wrapper')
        for idx, wrapper in enumerate(wrappers):
            iframe = wrapper.find('iframe', src=re.compile(r'player\.vimeo\.com'))
            if not iframe:
                continue
            vimeo_url = iframe['src']
            label = self._extract_video_meta_label(wrapper)
            if label:
                title = label
                slug = slugify_video_name(label)
            else:
                title = f"Video {idx + 1}"
                slug = f"Video-{idx + 1}"
            videos.append({
                'title': title,
                'slug': slug,
                'vimeo_url': vimeo_url,
            })

        if videos:
            return videos

        # Strategy 2: fallback — find iframes directly
        iframes = soup.find_all('iframe', src=re.compile(r'player\.vimeo\.com'))
        for idx, iframe in enumerate(iframes):
            vimeo_url = iframe['src']
            label = self._find_preceding_label(iframe)
            if label:
                title = label
                slug = slugify_video_name(label)
            else:
                title = f"Video {idx + 1}"
                slug = f"Video-{idx + 1}"
            videos.append({
                'title': title,
                'slug': slug,
                'vimeo_url': vimeo_url,
            })

        return videos

    def _extract_video_meta_label(self, wrapper):
        """Extract video label from amruta.org video-meta-info div.

        Format: "YYYY-MM-DD Title, Location, Country, Source, Duration′"
        We extract just the title part (between date and location comma).
        """
        meta_div = wrapper.find('div', class_='video-meta-info')
        if not meta_div:
            return None
        text = meta_div.get_text(strip=True)
        if not text:
            return None
        # Strip leading date "YYYY-MM-DD "
        text = re.sub(r'^\d{4}-\d{2}-\d{2}\s+', '', text)
        # Split by comma, take first part as title
        parts = text.split(',')
        if parts:
            return parts[0].strip()
        return text.strip()

    def _find_preceding_label(self, iframe):
        """Find the text/heading before an iframe element."""
        # Walk backwards through siblings
        node = iframe
        while True:
            node = node.previous_sibling
            if node is None:
                break
            if isinstance(node, Tag):
                if node.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b'):
                    text = node.get_text(strip=True)
                    if text:
                        return text
                if node.name == 'p':
                    strong = node.find(['strong', 'b'])
                    if strong:
                        text = strong.get_text(strip=True)
                        if text:
                            return text
                    text = node.get_text(strip=True)
                    if text and len(text) < 60:
                        return text
                if node.name == 'iframe':
                    break
        parent = iframe.parent
        if parent and parent.name in ('div', 'p', 'figure'):
            return self._find_preceding_label(parent)
        return None

    def extract_srt_links(self, soup):
        """Find SRT/VTT download links on the page."""
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.endswith(('.srt', '.vtt')):
                text = a.get_text(strip=True) or os.path.basename(href)
                links.append({'url': href, 'label': text, 'ext': os.path.splitext(href)[1]})
        return links

    def download_vimeo_subs(self, vimeo_url, output_dir):
        """Download English subtitles from Vimeo via yt-dlp, rename to en.srt."""
        os.makedirs(output_dir, exist_ok=True)
        cmd = [
            'yt-dlp',
            '--referer', 'https://www.amruta.org/',
            '--write-subs', '--sub-langs', 'en',
            '--skip-download',
            '--sub-format', 'srt/vtt/best',
            '--convert-subs', 'srt',
            '-o', os.path.join(output_dir, '%(id)s.%(ext)s'),
            vimeo_url,
        ]
        subprocess.run(cmd, check=True)

        # Rename {vimeo_id}.{lang}.srt -> {lang}.srt
        downloaded = []
        for f in globmod.glob(os.path.join(output_dir, '*.srt')):
            basename = os.path.basename(f)
            parts = basename.rsplit('.', 2)  # e.g. ['333507352', 'en', 'srt']
            if len(parts) == 3:
                lang = parts[1]
                new_path = os.path.join(output_dir, f"{lang}.srt")
                os.rename(f, new_path)
                downloaded.append(new_path)
            else:
                downloaded.append(f)
        return downloaded

    def extract_transcript(self, soup):
        """Extract transcript text from page content."""
        content = soup.find('div', class_='entry-content')
        if not content:
            content = soup.find('article')
        if not content:
            return None

        for tag in content.find_all(['script', 'style', 'iframe']):
            tag.decompose()

        text = content.get_text(separator='\n', strip=True)
        return text if text else None

    def download_file(self, url, output_path):
        """Download a file to disk."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        resp = self.session.get(url, stream=True)
        resp.raise_for_status()
        with open(output_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return output_path

    def download_video(self, vimeo_url, output_path):
        """Download video via yt-dlp with amruta.org referer."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        cmd = [
            'yt-dlp',
            '--referer', 'https://www.amruta.org/',
            '-o', output_path,
            vimeo_url,
        ]
        subprocess.run(cmd, check=True)
        return output_path

    def download_talk_all(self, url, talk_dir, what='srt,text'):
        """Download all videos from a talk page.

        Creates named subdirectories per video. Downloads SRTs per video
        from Vimeo. Transcript goes to talk root.

        Args:
            url: amruta.org talk page URL
            talk_dir: talk root directory (e.g. talks/1993-09-19_ganesha-puja)
            what: comma-separated list of {all,srt,text,video}

        Returns:
            dict with keys: title, videos, transcript_path
        """
        what_set = set(what.split(','))
        do_all = 'all' in what_set

        soup = self.fetch_talk_page(url)
        title = self.extract_title(soup)
        videos = self.extract_video_labels(soup)

        if not videos:
            print("  WARNING: No Vimeo videos found on page")

        result = {
            'title': title,
            'videos': videos,
            'transcript_path': None,
        }

        # Download SRTs per video
        if do_all or 'srt' in what_set:
            for video in videos:
                source_dir = os.path.join(talk_dir, video['slug'], 'source')
                os.makedirs(source_dir, exist_ok=True)
                print(f"  Downloading SRTs for: {video['title']}")
                srt_files = self.download_vimeo_subs(video['vimeo_url'], source_dir)
                video['srt_files'] = srt_files
                for f in srt_files:
                    print(f"    Downloaded: {os.path.basename(f)}")

        # Extract transcript text (talk-level, save at talk root)
        if do_all or 'text' in what_set:
            transcript = self.extract_transcript(soup)
            if transcript:
                os.makedirs(talk_dir, exist_ok=True)
                path = os.path.join(talk_dir, 'transcript_en.txt')
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(transcript)
                result['transcript_path'] = path
                print(f"  Saved transcript: transcript_en.txt")

        # Download videos
        if do_all or 'video' in what_set:
            for video in videos:
                source_dir = os.path.join(talk_dir, video['slug'], 'source')
                video_path = os.path.join(source_dir, 'video.mp4')
                print(f"  Downloading video: {video['title']}")
                self.download_video(video['vimeo_url'], video_path)

        return result


def setup_talk(talk_dir, url, date, slug, title, videos):
    """Create meta.yaml, video subdirs, and CLAUDE.md for a talk.

    Args:
        talk_dir: talk root directory
        url: amruta.org URL
        date: talk date (YYYY-MM-DD)
        slug: talk slug
        title: talk title
        videos: list of {title, slug, vimeo_url} dicts
    """
    os.makedirs(talk_dir, exist_ok=True)

    # Create video subdirectories
    for video in videos:
        video_dir = os.path.join(talk_dir, video['slug'])
        os.makedirs(os.path.join(video_dir, 'source'), exist_ok=True)
        os.makedirs(os.path.join(video_dir, 'work'), exist_ok=True)
        os.makedirs(os.path.join(video_dir, 'final'), exist_ok=True)

    # Detect location from title or URL
    location = ''
    search_text = f"{title or ''} {url}".lower()
    for place in ['Cabella', 'Lodge Hill', 'Nirmala Palace', 'Vienna', 'London',
                  'New Delhi', 'Mumbai', 'Pune', 'Rome', 'Paris', 'Sydney']:
        if place.lower() in search_text:
            location = place
            break

    # meta.yaml at talk root
    meta = {
        'title': title or slug,
        'date': date,
        'location': location,
        'amruta_url': url,
        'language': 'uk',
        'videos': [
            {
                'slug': v['slug'],
                'title': v['title'],
                'vimeo_url': v['vimeo_url'],
            }
            for v in videos
        ],
    }
    meta_path = os.path.join(talk_dir, 'meta.yaml')
    with open(meta_path, 'w', encoding='utf-8') as f:
        yaml.dump(meta, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"  Created: meta.yaml")

    # CLAUDE.md from template
    template_path = os.path.join('templates', 'CLAUDE_talk.md')
    if os.path.exists(template_path):
        with open(template_path, encoding='utf-8') as f:
            template = f.read()
        claude_md = template.replace('{{DATE}}', date).replace('{{SLUG}}', slug)
        talk_id = f"{date}_{slug}"
        claude_md = claude_md.replace('{{TALK_ID}}', talk_id)
        # Add video list
        video_list = '\n'.join(f"- `{v['slug']}/`" for v in videos)
        claude_md = claude_md.replace('{{VIDEOS}}', video_list)
    else:
        claude_md = f"# {slug} — {date}\n"

    claude_path = os.path.join(talk_dir, 'CLAUDE.md')
    with open(claude_path, 'w', encoding='utf-8') as f:
        f.write(claude_md)
    print(f"  Created: CLAUDE.md")


def process_single_url(downloader, url, what, slug_override=None):
    """Process a single amruta.org URL."""
    date, url_slug = parse_amruta_url(url)
    slug = slug_override or url_slug
    talk_id = f"{date}_{slug}"
    talk_dir = os.path.join('talks', talk_id)

    print(f"\nDownloading talk: {talk_id}")
    print(f"  URL: {url}")

    result = downloader.download_talk_all(url, talk_dir, what)

    setup_talk(
        talk_dir=talk_dir,
        url=url,
        date=date,
        slug=slug,
        title=result['title'],
        videos=result['videos'],
    )

    print(f"\nDone: talks/{talk_id}/")
    print(f"  Title: {result['title']}")
    print(f"  Videos: {len(result['videos'])}")
    for v in result['videos']:
        print(f"    - {v['slug']}: {v['vimeo_url']}")
    if result['transcript_path']:
        print(f"  Transcript: {result['transcript_path']}")

    return talk_id


def main():
    parser = argparse.ArgumentParser(description='Download talk(s) from amruta.org')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--url', help='amruta.org talk page URL')
    group.add_argument('--manifest', help='Batch manifest YAML file (e.g. queue.yaml)')
    parser.add_argument('--slug', help='Override slug (single URL mode only)')
    parser.add_argument('--what', default='srt,text', help='What to download: all,srt,text,video')
    parser.add_argument('--cookie', help='Session cookie (overrides env)')
    args = parser.parse_args()

    downloader = AmrutaDownloader(session_cookie=args.cookie)

    if args.url:
        process_single_url(downloader, args.url, args.what, args.slug)
    else:
        with open(args.manifest, encoding='utf-8') as f:
            manifest = yaml.safe_load(f)
        talks = manifest.get('talks', [])
        print(f"Batch mode: {len(talks)} talk(s) to process")
        for entry in talks:
            url = entry['url']
            slug_override = entry.get('slug')
            try:
                process_single_url(downloader, url, args.what, slug_override)
            except Exception as e:
                print(f"\nERROR processing {url}: {e}")
                continue


if __name__ == '__main__':
    main()
