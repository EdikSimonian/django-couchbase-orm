"""django-couchbase-orm: A Couchbase ORM for Django applications."""

__version__ = "0.5.0"

from django_couchbase_orm.aggregates import Avg, Count, Max, Min, Sum
from django_couchbase_orm.document import Document
from django_couchbase_orm.exceptions import (
    DocumentDoesNotExist,
    MultipleDocumentsReturned,
    OperationError,
    ValidationError,
)
from django_couchbase_orm.fields.compound import (
    DictField,
    EmbeddedDocument,
    EmbeddedDocumentField,
    ListField,
)
from django_couchbase_orm.fields.datetime import DateField, DateTimeField
from django_couchbase_orm.fields.reference import ReferenceField
from django_couchbase_orm.fields.simple import (
    BooleanField,
    FloatField,
    IntegerField,
    StringField,
    UUIDField,
)
from django_couchbase_orm.paginator import CouchbasePaginator
from django_couchbase_orm.queryset.q import Q

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
