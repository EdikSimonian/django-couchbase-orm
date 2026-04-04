from django.db import models
from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel


class HomePage(Page):
    """A simple home page with a body field."""

    body = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("body"),
    ]


class BlogIndexPage(Page):
    """Blog index page that lists child BlogPages."""

    intro = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
    ]

    subpage_types = ["home.BlogPage"]

    def get_context(self, request):
        context = super().get_context(request)
        context["posts"] = (
            self.get_children().live().specific().order_by("-blogpage__date")
        )
        return context


class BlogPage(Page):
    """A blog post page."""

    date = models.DateField("Post date", null=True, blank=True)
    intro = models.CharField(max_length=250, blank=True, default="")
    body = RichTextField(blank=True)
    # Denormalized from Page for mobile sync (so home_blogpage doc has title)
    blog_title = models.CharField(max_length=255, blank=True, default="", editable=False)
    blog_slug = models.CharField(max_length=255, blank=True, default="", editable=False)

    content_panels = Page.content_panels + [
        FieldPanel("date"),
        FieldPanel("intro"),
        FieldPanel("body"),
    ]

    parent_page_types = ["home.BlogIndexPage"]

    def save(self, **kwargs):
        self.blog_title = self.title
        self.blog_slug = self.slug
        super().save(**kwargs)
