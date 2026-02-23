"""Download materials from amruta.org.

Fetches SRT subtitles, transcript text, and extracts Vimeo video URLs
from amruta.org talk pages using WordPress session cookie authentication.

Usage:
    python -m tools.download --url URL --talk-dir PATH --what {all,srt,text,video}
"""

import argparse
import os
import re
import subprocess

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


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
        resp.raise_for_status()
        return BeautifulSoup(resp.text, 'html.parser')

    def extract_vimeo_url(self, soup):
        """Extract Vimeo video URL from iframe."""
        iframe = soup.find('iframe', src=re.compile(r'player\.vimeo\.com'))
        if iframe:
            return iframe['src']
        # Also check for data attributes or script tags
        for script in soup.find_all('script'):
            text = script.string or ''
            match = re.search(r'player\.vimeo\.com/video/(\d+)(?:\?h=([a-f0-9]+))?', text)
            if match:
                vid = match.group(1)
                h = match.group(2)
                if h:
                    return f"https://player.vimeo.com/video/{vid}?h={h}"
                return f"https://player.vimeo.com/video/{vid}"
        return None

    def extract_all_vimeo_urls(self, soup):
        """Extract all Vimeo video URLs from iframes."""
        urls = []
        for iframe in soup.find_all('iframe', src=re.compile(r'player\.vimeo\.com')):
            urls.append(iframe['src'])
        return urls

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
        """Download subtitles from Vimeo via yt-dlp --write-subs."""
        import glob as globmod
        os.makedirs(output_dir, exist_ok=True)
        cmd = [
            'yt-dlp',
            '--referer', 'https://www.amruta.org/',
            '--write-subs', '--all-subs', '--skip-download',
            '--sub-format', 'srt/vtt/best',
            '--convert-subs', 'srt',
            '-o', os.path.join(output_dir, '%(id)s.%(ext)s'),
            vimeo_url,
        ]
        subprocess.run(cmd, check=True)
        return globmod.glob(os.path.join(output_dir, '*.srt'))

    def extract_transcript(self, soup):
        """Extract transcript text from page content."""
        # Look for common transcript containers
        content = soup.find('div', class_='entry-content')
        if not content:
            content = soup.find('article')
        if not content:
            return None

        # Remove script/style tags
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

    def download_talk(self, url, talk_dir, what='all'):
        """Download materials from a talk page.

        Args:
            url: amruta.org talk page URL
            talk_dir: directory to save files to
            what: comma-separated list of {all,srt,text,video}

        Returns:
            dict with keys: srt_files, transcript_path, vimeo_url
        """
        what_set = set(what.split(','))
        do_all = 'all' in what_set

        soup = self.fetch_talk_page(url)
        result = {'srt_files': [], 'transcript_path': None, 'vimeo_url': None}

        # Extract Vimeo URL (always, for meta.yaml)
        result['vimeo_url'] = self.extract_vimeo_url(soup)

        # Download SRTs — try direct links first, then Vimeo text tracks
        if do_all or 'srt' in what_set:
            srt_links = self.extract_srt_links(soup)
            if srt_links:
                for link in srt_links:
                    filename = os.path.basename(link['url'])
                    out = self.download_file(link['url'], os.path.join(talk_dir, filename))
                    result['srt_files'].append(out)
                    print(f"  Downloaded SRT: {filename}")
            elif result['vimeo_url']:
                # No direct SRT links — extract from Vimeo text tracks
                print("  No direct SRT links found, extracting from Vimeo...")
                srt_files = self.download_vimeo_subs(result['vimeo_url'], talk_dir)
                result['srt_files'] = srt_files
                for f in srt_files:
                    print(f"  Downloaded SRT: {os.path.basename(f)}")

        # Extract transcript text
        if do_all or 'text' in what_set:
            transcript = self.extract_transcript(soup)
            if transcript:
                path = os.path.join(talk_dir, 'transcript_en.txt')
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(transcript)
                result['transcript_path'] = path
                print(f"  Saved transcript: transcript_en.txt")

        # Download video
        if do_all or 'video' in what_set:
            if result['vimeo_url']:
                video_path = os.path.join(talk_dir, 'video.mp4')
                self.download_video(result['vimeo_url'], video_path)
                print(f"  Downloaded video")

        return result


def main():
    parser = argparse.ArgumentParser(description='Download from amruta.org')
    parser.add_argument('--url', required=True, help='amruta.org talk page URL')
    parser.add_argument('--talk-dir', required=True, help='Output directory')
    parser.add_argument('--what', default='srt,text', help='What to download: all,srt,text,video')
    parser.add_argument('--cookie', help='Session cookie (overrides env)')
    args = parser.parse_args()

    downloader = AmrutaDownloader(session_cookie=args.cookie)
    result = downloader.download_talk(args.url, args.talk_dir, args.what)

    print(f"\nDone. Vimeo URL: {result['vimeo_url']}")
    print(f"SRT files: {len(result['srt_files'])}")


if __name__ == '__main__':
    main()
