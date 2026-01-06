from django.contrib import admin
from .models import (
    AudioFile,
    TranscriptSegment,
    Summary,
    ToDoItem,
    EmailSummary,
    ImportantPoint
)

# In-line admin classes for better organization
class TranscriptSegmentInline(admin.TabularInline):
    model = TranscriptSegment
    extra = 0

class SummaryInline(admin.StackedInline):
    model = Summary

class ToDoItemInline(admin.TabularInline):
    model = ToDoItem
    extra = 0

class EmailSummaryInline(admin.StackedInline):
    model = EmailSummary

class ImportantPointInline(admin.TabularInline):
    model = ImportantPoint
    extra = 0

@admin.register(AudioFile)
class AudioFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'user', 'uploaded_at')
    list_filter = ('user', 'uploaded_at')
    search_fields = ('title', 'user__username')
    inlines = [
        SummaryInline,
        EmailSummaryInline,
        ImportantPointInline,
        ToDoItemInline,
        TranscriptSegmentInline,
    ]

# Baki models ko bhi register kar dete hain (optional, but good)
@admin.register(ImportantPoint)
class ImportantPointAdmin(admin.ModelAdmin):
    list_display = ('id', 'text', 'audio_id', 'is_added_to_calendar')
    list_filter = ('is_added_to_calendar',)
    search_fields = ('text',)

@admin.register(ToDoItem)
class ToDoItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'text', 'audio_id', 'is_done')
    list_filter = ('is_done',)
    search_fields = ('text',)