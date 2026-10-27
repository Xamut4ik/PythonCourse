import time

from django.conf import settings
from django.core.cache import cache, caches
from django.core.cache.utils import make_template_fragment_key

BOOK_DETAIL_TIMEOUT = 60 * 15
LIST_TIMEOUT = 60 * 5
PAGES_CACHE = 'pages'
LIST_VARY_HEADERS = ('Accept', 'Authorization', 'Cookie')
CATALOG_VERSION_KEY = 'catalog_version'
BOOK_DETAIL_FRAGMENT = 'book_detail'
CATALOG_CATEGORIES_FRAGMENT = 'catalog_categories'


def book_detail_key(book_id):
    return f'book_detail_{book_id}'


def language_codes():
    return [code for code, _name in settings.LANGUAGES]


def book_fragment_keys(book_id):
    return [make_template_fragment_key(BOOK_DETAIL_FRAGMENT, [book_id, code]) for code in language_codes()]


def catalog_fragment_keys():
    return [make_template_fragment_key(CATALOG_CATEGORIES_FRAGMENT, [code]) for code in language_codes()]


def get_catalog_version():
    version = cache.get(CATALOG_VERSION_KEY)
    if version is None:
        version = time.time_ns()
        cache.add(CATALOG_VERSION_KEY, version, None)
        version = cache.get(CATALOG_VERSION_KEY, version)
    return version


def clear_page_cache():
    page_cache = caches[PAGES_CACHE]
    if hasattr(page_cache, 'delete_pattern'):
        page_cache.delete_pattern('*')
    else:
        page_cache.clear()


def invalidate_catalog():
    cache.set(CATALOG_VERSION_KEY, time.time_ns(), None)
    cache.delete_many(catalog_fragment_keys())
    clear_page_cache()


def invalidate_books(book_ids):
    keys = []
    for book_id in book_ids:
        keys.append(book_detail_key(book_id))
        keys.extend(book_fragment_keys(book_id))
    if keys:
        cache.delete_many(keys)
    invalidate_catalog()
