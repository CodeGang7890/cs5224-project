from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

MAX_PAGE_SIZE = 100


class DetailedPageNumberPagination(PageNumberPagination):
    """Page-number pagination with a client-chosen page size and explicit page info.

    Query parameters: `page` (1-based) and `page_size` (default `PAGE_SIZE` from settings, max
    `MAX_PAGE_SIZE`). Response:
    `{count, total_pages, current_page, page_size, has_next, has_previous, next, previous, results}`.
    An out-of-range page returns 404, like DRF's default pagination.
    """

    page_size_query_param = 'page_size'
    max_page_size = MAX_PAGE_SIZE

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'page_size': self.page.paginator.per_page,
            'has_next': self.page.has_next(),
            'has_previous': self.page.has_previous(),
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'required': [
                'count', 'total_pages', 'current_page', 'page_size', 'has_next', 'has_previous',
                'next', 'previous', 'results',
            ],
            'properties': {
                'count': {'type': 'integer', 'example': 42, 'description': 'Number of items across all pages.'},
                'total_pages': {'type': 'integer', 'example': 3},
                'current_page': {'type': 'integer', 'example': 1},
                'page_size': {'type': 'integer', 'example': 20},
                'has_next': {'type': 'boolean', 'example': True},
                'has_previous': {'type': 'boolean', 'example': False},
                'next': {'type': 'string', 'nullable': True, 'format': 'uri', 'description': 'URL of the next page.'},
                'previous': {'type': 'string', 'nullable': True, 'format': 'uri', 'description': 'URL of the previous page.'},
                'results': schema,
            },
        }
