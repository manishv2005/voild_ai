from django.db import models

# User model ko import karein
from django.contrib.auth.models import User 

class AudioFile(models.Model):
    """
    Main uploaded audio file. Acts as the parent for all derived data.
    """
    # YEH NAYI FIELD ADD KAREIN:
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="audio_files")

    title = models.CharField(max_length=255, blank=True, null=True)
    audio_file = models.FileField(upload_to='uploads/audio/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    keep_note_name = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.title or f"Audio {self.id}"


class TranscriptSegment(models.Model):
    """
    Each line/segment of transcript with timestamps and speaker name.
    """
    audio = models.ForeignKey(AudioFile, related_name='transcripts', on_delete=models.CASCADE)
    speaker = models.CharField(max_length=100, blank=True, null=True)
    start_time = models.CharField(max_length=50, help_text="Start time (e.g., 00:00:03)")
    end_time = models.CharField(max_length=50, help_text="End time (e.g., 00:00:08)")
    text = models.TextField()

    def __str__(self):
        return f"{self.speaker or 'Unknown'}: {self.text[:50]}..."


class Summary(models.Model):
    """
    Overall summary of the audio file.
    """
    audio = models.OneToOneField(AudioFile, related_name='summary', on_delete=models.CASCADE)
    text = models.TextField()

    def __str__(self):
        return f"Summary of {self.audio}"


class ToDoItem(models.Model):
    """
    To-do items extracted from conversation.
    """
    audio = models.ForeignKey(AudioFile, related_name='todos', on_delete=models.CASCADE)
    text = models.TextField()
    is_done = models.BooleanField(default=False)

    def __str__(self):
        return f"TODO: {self.text[:40]}{'...' if len(self.text) > 40 else ''}"


class EmailSummary(models.Model):
    """
    Email-friendly summary or formatted version.
    """
    audio = models.OneToOneField(AudioFile, related_name='email', on_delete=models.CASCADE)
    text = models.TextField(help_text="Text content to be used in email body")

    def __str__(self):
        return f"Email Summary for {self.audio}"


class ImportantPoint(models.Model):
    """
    Important points extracted from audio (as bullet points).
    """
    audio = models.ForeignKey(AudioFile, related_name='important_points', on_delete=models.CASCADE)
    text = models.TextField()
    is_added_to_calendar = models.BooleanField(default=False)   
    def __str__(self):
        return f" {self.text[:60]}"


class EmailDraft(models.Model):
    audio = models.OneToOneField(AudioFile, related_name='email_draft', on_delete=models.CASCADE)
    to_email = models.EmailField(blank=True, null=True)
    to_name = models.CharField(max_length=255, blank=True, null=True)
    subject = models.CharField(max_length=255, blank=True, null=True)
    body = models.TextField(blank=True, null=True)
    is_needed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Draft for {self.audio}"