from django.conf import settings
from django.db import models

class Membership(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    interests = models.CharField(max_length=200)
    testimony = models.TextField()
    experience = models.TextField()
    role = models.CharField(max_length=20, choices=[('pending', 'Awaiting approval'), ('commenter', 'Commenter'), ('contributor', 'Contributor'), ('reviewer', 'Experienced reviewer')], default='pending')
    def __str__(self): return f'{self.user} — {self.get_role_display()}'

class Song(models.Model):
    title = models.CharField(max_length=200)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    stage = models.CharField(max_length=12, choices=[('draft', 'In development'), ('frozen', 'Frozen review'), ('published', 'Published')], default='draft')
    revision = models.PositiveIntegerField(default=1)
    author_signed = models.BooleanField(default=False)
    rework_requested = models.BooleanField(default=False)
    updated = models.DateTimeField(auto_now=True)
    def __str__(self): return self.title

class Part(models.Model):
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='parts')
    kind = models.CharField(max_length=10, choices=[('concept', 'Concept'), ('lyrics', 'Lyrics'), ('tune', 'Tune')])
    content = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['song', 'kind'], name='unique_song_part')]

class Revision(models.Model):
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name="history")
    number = models.PositiveIntegerField()
    content = models.TextField()
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created = models.DateTimeField(auto_now_add=True)

class Approval(models.Model):
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='approvals')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    scope = models.CharField(max_length=12)
    revision = models.PositiveIntegerField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['song', 'user', 'scope', 'revision'], name='unique_approval')]

class Comment(models.Model):
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    scope = models.CharField(max_length=12, choices=[('concept','Concept'),('lyrics','Lyrics'),('tune','Tune'),('review','Frozen review')])
    revision = models.PositiveIntegerField()
    anchor = models.CharField(max_length=500, blank=True, help_text='Quoted phrase or measure/note reference')
    body = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['created']

class EditLock(models.Model):
    part = models.OneToOneField(Part, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expires = models.DateTimeField()
