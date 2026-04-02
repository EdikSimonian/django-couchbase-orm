"""Django-CB: A Couchbase ORM for Django applications."""

__version__ = "0.2.0"

from django_cb.aggregates import Avg, Count, Max, Min, Sum
from django_cb.document import Document
from django_cb.exceptions import (
    DocumentDoesNotExist,
    MultipleDocumentsReturned,
    OperationError,
    ValidationError,
)
from django_cb.fields.compound import (
    DictField,
    EmbeddedDocument,
    EmbeddedDocumentField,
    ListField,
)
from django_cb.fields.datetime import DateField, DateTimeField
from django_cb.fields.reference import ReferenceField
from django_cb.fields.simple import (
    BooleanField,
    FloatField,
    IntegerField,
    StringField,
    UUIDField,
)
from django_cb.paginator import CouchbasePaginator
from django_cb.queryset.q import Q

__all__ = [
    "Document",
    "DocumentDoesNotExist",
    "MultipleDocumentsReturned",
    "OperationError",
    "ValidationError",
    "BooleanField",
    "DateField",
    "DateTimeField",
    "DictField",
    "EmbeddedDocument",
    "EmbeddedDocumentField",
    "FloatField",
    "IntegerField",
    "ListField",
    "Avg",
    "Count",
    "CouchbasePaginator",
    "Max",
    "Min",
    "Q",
    "ReferenceField",
    "Sum",
    "StringField",
    "UUIDField",
]
