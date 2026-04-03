from django.db import models


class Article(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField(default="")
    published = models.BooleanField(default=False)
    views = models.IntegerField(default=0)
    author = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "testapp"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    articles = models.ManyToManyField(Article, related_name="tags", blank=True)

    class Meta:
        app_label = "testapp"

    def __str__(self):
        return self.name
