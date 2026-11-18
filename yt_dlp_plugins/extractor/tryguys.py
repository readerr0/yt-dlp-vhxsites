import functools
import html
import re

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.extractor.vimeo import VHXEmbedIE
from yt_dlp.utils import (
    ExtractorError,
    OnDemandPagedList,
    int_or_none,
    traverse_obj,
    unified_strdate,
    urlencode_postdata,
)

_BASE_URL = 'https://watch.2ndtry.tv'


class _TryguysBaseIE(InfoExtractor):
    _LOGIN_URL = f'{_BASE_URL}/login'
    _NETRC_MACHINE = '2ndtry'

    def _extract_props(self, webpage, display_id):
        return self._parse_json(html.unescape(self._search_regex(
            r'\bdata-props="(\{[^"]+\})"', webpage, 'page props')), display_id)

    def _login(self, display_id):
        username, password = self._get_login_info()
        if not username:
            return False

        login_page = self._download_webpage(
            self._LOGIN_URL, display_id, note='Getting authenticity token')
        self._download_webpage(
            self._LOGIN_URL, display_id, note='Logging in', fatal=False,
            data=urlencode_postdata({
                'email': username,
                'password': password,
                'authenticity_token': self._html_search_regex(
                    r'name=["\']authenticity_token["\'] value=["\'](.+?)["\']',
                    login_page, 'authenticity_token'),
                'utf8': True,
            }))
        return True

    def _download_props(self, url, display_id, is_authorized):
        """Download a page and its props. If is_authorized(props) is false, log in and download it again."""
        webpage = props = None
        if self._get_cookies(_BASE_URL).get('_session'):
            webpage = self._download_webpage(url, display_id)
            props = self._extract_props(webpage, display_id)
        if props is None or not is_authorized(props):
            logged_in = self._login(display_id)
            webpage = self._download_webpage(url, display_id)
            props = self._extract_props(webpage, display_id)
            if not is_authorized(props):
                if not logged_in:
                    self.raise_login_required(method='any')
                if not traverse_obj(props, ('account', 'id')):
                    raise ExtractorError('Incorrect username/password', expected=True)
                raise ExtractorError('Account is not subscribed', expected=True)
        return webpage, props


class TryguysIE(_TryguysBaseIE):
    _VALID_URL = r'https?://(?:watch\.)?2ndtry\.tv/(?:[^/]+/)*videos/(?P<id>[^/?#]+)/?(?:[?#]|$)'

    def _real_extract(self, url):
        display_id = self._match_id(url)
        _, props = self._download_props(
            url, display_id, lambda p: traverse_obj(p, 'video') and not traverse_obj(p, ('video', 'paywall')))
        video = props['video']

        embed_url = video['playerUrl']
        season_info = video.get('seasonInfo') or ''
        episode_number = int_or_none(self._search_regex(r'\bE(\d+)', season_info, 'episode', default=None))
        title = video.get('title')
        thumbnail = video.get('posterUrl')

        return {
            '_type': 'url_transparent',
            'ie_key': VHXEmbedIE.ie_key(),
            'url': VHXEmbedIE._smuggle_referrer(embed_url, _BASE_URL),
            'id': str(video.get('id') or VHXEmbedIE._match_id(embed_url)),
            'display_id': display_id,
            'title': title,
            'description': video.get('description'),
            'thumbnail': thumbnail.split('?')[0] if thumbnail else None,  # Ignore crop/downscale
            'duration': int_or_none(video.get('durationSeconds')),
            'series': traverse_obj(video, ('badges', lambda _, v: v.get('url'), 'label'), get_all=False),
            'season_number': int_or_none(self._search_regex(r'\bS(\d+)', season_info, 'season', default=None)),
            'episode_number': episode_number,
            'episode': title if episode_number else None,
            'release_date': unified_strdate(traverse_obj(video, (
                'descriptionMetadata', lambda _, v: v['kind'] == 'release_dates', 'values', 0, 'primary'),
                get_all=False)),
        }


class TryguysSeasonIE(_TryguysBaseIE):
    _PAGE_SIZE = 24
    _VALID_URL = r'https?://(?:watch\.)?2ndtry\.tv/(?P<id>[^/?#&]+)(?:/season:(?P<season>[0-9]+))?/?(?:[?#]|$)'

    def _fetch_page(self, api_url, token, playlist_id, page):
        page += 1
        data = self._download_json(
            api_url, playlist_id, note=f'Downloading page {page}',
            headers={'Authorization': f'Bearer {token}'},
            query={'page': page, 'per_page': self._PAGE_SIZE})
        for item in traverse_obj(data, ('items', ..., 'entity')):
            page_url = item.get('page_url')
            if not page_url:
                continue
            if re.search(r'/videos/', page_url):
                yield self.url_result(
                    page_url, TryguysIE, str(item.get('id')), item.get('title') or item.get('name'),
                    description=item.get('short_description'),
                    duration=traverse_obj(item, ('duration', 'seconds')),
                    episode_number=traverse_obj(item, ('metadata', 'season', 'episode_number')),
                    season_number=traverse_obj(item, ('metadata', 'season', 'number')))
            else:
                yield self.url_result(page_url, TryguysSeasonIE)

    def _real_extract(self, url):
        slug, season_num = self._match_valid_url(url).group('id', 'season')
        webpage, props = self._download_props(url, slug, lambda p: traverse_obj(p, ('account', 'id')))
        collection = traverse_obj(props, 'collection', expected_type=dict)
        if not collection:
            raise ExtractorError('Page is not a collection', expected=True)

        site_id = traverse_obj(props, ('site', 'id'))
        token = traverse_obj(props, ('apiV2', 'token'))
        api_base = traverse_obj(props, ('apiV2', 'url')) or 'https://api.vhx.com'
        title = self._html_search_meta(
            ('og:title', 'twitter:title'), webpage, 'title', default=slug).rsplit(' - ', 1)[0]

        collection_id = collection['id']
        playlist_id, playlist_title = slug, title
        seasons = traverse_obj(collection, ('series', 'seasons', ...))
        if seasons:
            season_num = int(season_num or 1)
            season = traverse_obj(seasons, (lambda _, v: v['number'] == season_num), get_all=False)
            if not season:
                raise ExtractorError(f'Season {season_num} not found', expected=True)
            collection_id = season['id']
            playlist_id = f'{slug}-season-{season_num}'
            playlist_title = f'{title} - {season.get("name") or f"Season {season_num}"}'

        api_url = f'{api_base}/v2/sites/{site_id}/collections/{collection_id}/items'
        return self.playlist_result(
            OnDemandPagedList(functools.partial(self._fetch_page, api_url, token, playlist_id), self._PAGE_SIZE),
            playlist_id, playlist_title)
