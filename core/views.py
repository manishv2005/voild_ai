from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone

from .models import AudioFile, TranscriptSegment, Summary, ToDoItem, EmailSummary, ImportantPoint

import requests
import json
import socket
import os
import re
from datetime import datetime, timedelta, time
from dateutil import parser  # Requires: pip install python-dateutil
from allauth.socialaccount.models import SocialToken, SocialApp
import base64
from email.message import EmailMessage
import subprocess
import shutil

# Helper: Format timestamp
def format_timestamp(seconds_float):
    hours = int(seconds_float // 3600)
    minutes = int((seconds_float % 3600) // 60)
    seconds = int(seconds_float % 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


@login_required
def dashboard(request):
    audio_files = AudioFile.objects.filter(user=request.user).order_by('-uploaded_at')
    return render(request, 'core/dashboard.html', {'audio_files': audio_files})


@login_required
def upload_audio(request):
    if request.method != 'POST':
        return redirect('dashboard')

    title = request.POST.get('title')
    audio_file = request.FILES.get('audio_file')

    if not audio_file or not title:
        messages.error(request, "Missing title or audio file.")
        return redirect('dashboard')

    # STEP 0: Create AudioFile instance
    audio_obj = AudioFile.objects.create(
        user=request.user,
        title=title,
        audio_file=audio_file
    )
    print(f"[0] AudioFile created (ID: {audio_obj.id})")

    # If the recording is WebM, try converting to MP3 using ffmpeg (if available)
    try:
        src_path = audio_obj.audio_file.path
        if src_path.lower().endswith('.webm') and shutil.which('ffmpeg'):
            mp3_path = os.path.splitext(src_path)[0] + '.mp3'
            cmd = ['ffmpeg', '-y', '-i', src_path, '-vn', '-acodec', 'libmp3lame', '-b:a', '192k', mp3_path]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode == 0 and os.path.exists(mp3_path):
                rel = os.path.relpath(mp3_path, settings.MEDIA_ROOT).replace('\\','/')
                audio_obj.audio_file.name = rel
                audio_obj.save(update_fields=['audio_file'])
    except Exception as _:
        pass

    # Create raw data directory
    raw_data_dir = os.path.join(settings.MEDIA_ROOT, 'raw_data')
    os.makedirs(raw_data_dir, exist_ok=True)

    # Backup original socket (for IPv4 force)
    original_getaddrinfo = socket.getaddrinfo

    try:
        def new_getaddrinfo(*args, **kwargs):
            responses = original_getaddrinfo(*args, **kwargs)
            return [res for res in responses if res[0] == socket.AF_INET]
        socket.getaddrinfo = new_getaddrinfo

        # STEP 1: ElevenLabs Transcription
        print("[1] Calling ElevenLabs API...")
        elevenlabs_url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {"xi-api-key": settings.ELEVENLABS_API_KEY}

        with open(audio_obj.audio_file.path, 'rb') as f:
            files_data = {
                'file': (audio_obj.audio_file.name, f, audio_file.content_type),
                'model_id': (None, 'scribe_v1'),
                'diarize': (None, 'true'),
                'timestamps_granularity': (None, 'word')
            }
            response = requests.post(elevenlabs_url, headers=headers, files=files_data, timeout=300)
            response.raise_for_status()
            transcript_json = response.json()

        # Save raw transcript file
        transcript_filepath = os.path.join(raw_data_dir, f'transcript_RAW_{audio_obj.id}.json')
        with open(transcript_filepath, 'w', encoding='utf-8') as f:
            json.dump(transcript_json, f, indent=4, ensure_ascii=False)
        print(f"[1.1] Transcript saved to file: {transcript_filepath}")

        print("[1.2] Saving transcript segments to DB...")

        utterances = transcript_json.get('utterances')

        # 🔸 If "utterances" not found, try to group from "words"
        if not utterances and 'words' in transcript_json:
            words = transcript_json['words']
            grouped = []
            if words:
                current_speaker = words[0]['speaker_id']
                start_time = words[0]['start']
                current_text = []

                for w in words:
                    if w['type'] == 'word':
                        if w['speaker_id'] != current_speaker:
                            # Save previous speaker utterance
                            grouped.append({
                                'speaker': current_speaker,
                                'start': start_time,
                                'end': prev_end,
                                'text': ' '.join(current_text).strip()
                            })
                            # Reset for new speaker
                            current_speaker = w['speaker_id']
                            start_time = w['start']
                            current_text = []
                        current_text.append(w['text'])
                        prev_end = w['end']

                # Save last one
                grouped.append({
                    'speaker': current_speaker,
                    'start': start_time,
                    'end': prev_end,
                    'text': ' '.join(current_text).strip()
                })

            utterances = grouped

        # 🔹 Now save utterances (either from API or from fallback grouping)
        for utt in utterances:
            TranscriptSegment.objects.create(
                audio=audio_obj,
                speaker=utt.get('speaker', 'Unknown'),
                start_time=format_timestamp(utt.get('start', 0)),
                end_time=format_timestamp(utt.get('end', 0)),
                text=utt.get('text', '')
            )

        print(f"[1.3] {len(utterances)} transcript segments saved to DB.")


        # STEP 2: Gemini Analysis
        print("[2] Calling Gemini API...")
        
        current_date_str = timezone.now().strftime("%Y-%m-%d")
        gemini_prompt = f"""
        You are a helpful assistant for a meeting analysis app.
        Today's date is {current_date_str}.
        I have a raw JSON transcript from an audio file.
        Analyze the transcript and return a single JSON object with these keys:
        1. "summary": string
        2. "todos": list of strings (concise action items)
        3. "important_points": list of strings (deadlines or key highlights)
        4. "email_draft": object with fields:
           - "is_needed": boolean (true only if the conversation clearly requests sending an email and it's important)
           - "to_name": string or null (recipient name if spoken)
           - "to_email": string or null (only if explicitly mentioned; otherwise null)
           - "subject": string (short, clear)
           - "body": string (polite, concise draft)
        Rules:
        - Detect phrases like "send an email to ...", "mail ...", etc. If unclear or low priority, set is_needed=false.
        - If only a name is mentioned (no email), still fill to_name and leave to_email null.
        - Keep body under 300 words.
        - Dates like "today" means {current_date_str}; "tomorrow" means {(timezone.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")}.
        Transcript data:
        ---
        {json.dumps(transcript_json)}
        ---
        """

        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        data = {"contents": [{"parts": [{"text": gemini_prompt}]}]}

        response = requests.post(gemini_url, headers=headers, data=json.dumps(data), timeout=180)
        response.raise_for_status()
        gemini_data = response.json()

        gemini_response_text = gemini_data['candidates'][0]['content']['parts'][0]['text']

        try:
            cleaned_text = gemini_response_text.strip()
            # Remove any markdown code block markers if present
            if cleaned_text.startswith("```"):
                cleaned_text = cleaned_text.strip("`")
                # Remove potential 'json' language tag
                cleaned_text = cleaned_text.replace("json", "", 1).strip()
            structured_data = json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            print(f"[2.1] JSON parse error: {e}")
            print("RAW Gemini response was:\n", gemini_response_text)
            raise Exception("Gemini returned invalid JSON format.")


        # Save raw Gemini JSON to file
        gemini_filepath = os.path.join(raw_data_dir, f'gemini_analysis_RAW_{audio_obj.id}.json')
        with open(gemini_filepath, 'w', encoding='utf-8') as f:
            json.dump(structured_data, f, indent=4, ensure_ascii=False)
        print(f"[2.2] Gemini analysis saved to file: {gemini_filepath}")

        # Save Gemini data to DB
        print("[2.3] Saving Gemini analysis to DB...")
        Summary.objects.create(audio=audio_obj, text=structured_data.get('summary', ''))
        email_draft_data = structured_data.get('email_draft', {}) or {}
        from .models import EmailDraft  # local import to avoid circulars if any
        EmailDraft.objects.update_or_create(
            audio=audio_obj,
            defaults={
                'to_name': email_draft_data.get('to_name'),
                'to_email': email_draft_data.get('to_email'),
                'subject': email_draft_data.get('subject'),
                'body': email_draft_data.get('body'),
                'is_needed': bool(email_draft_data.get('is_needed', False)),
            }
        )

        for todo in structured_data.get('todos', []):
            ToDoItem.objects.create(audio=audio_obj, text=todo, is_done=False)

        for point in structured_data.get('important_points', []):
            ImportantPoint.objects.create(audio=audio_obj, text=point)

        print("[2.4] Gemini analysis saved to DB.")

        # After saving TODOs, sync Google Keep note for this audio
        try:
            sync_keep_note_for_audio(request, audio_obj)
        except Exception:
            pass
        messages.success(request, f"'{title}' processed successfully! Data saved in DB and raw files.")

    except Exception as e:
        print("⚠️ Error processing audio:", e)
        if hasattr(e, 'response') and e.response is not None:
            print("API Response:", e.response.text)
        messages.error(request, f"Failed to process '{title}'. See logs for details.")

    finally:
        socket.getaddrinfo = original_getaddrinfo
        print("[✔] Socket restored.")

    return redirect('dashboard')


# ===================================================================
# 1. SUMMARY VIEW (The default analysis page)
# ===================================================================
@login_required
def summary_view(request, audio_id):
    audio_file = get_object_or_404(AudioFile, id=audio_id, user=request.user)
    try:
        summary = audio_file.summary
    except ObjectDoesNotExist:
        summary = None
    
    # Fetch important points as well
    important_points = audio_file.important_points.all()
        
    context = {
        'audio': audio_file,
        'summary': summary,
        'important_points': important_points, # Pass this to the template
        'active_page': 'summary' # 👈 To highlight the nav link
    }
    return render(request, 'core/summary.html', context)

# ===================================================================
# 2. TRANSCRIPTION VIEW
# ===================================================================
@login_required
def transcription_view(request, audio_id):
    audio_file = get_object_or_404(AudioFile, id=audio_id, user=request.user)
    transcripts = audio_file.transcripts.all().order_by('start_time')
        
    context = {
        'audio': audio_file,
        'transcripts': transcripts,
        'active_page': 'transcription' # 👈 To highlight the nav link
    }
    return render(request, 'core/transcription.html', context)

# ===================================================================
# 3. TO-DO VIEW
# ===================================================================
@login_required
def todo_view(request, audio_id):
    audio_file = get_object_or_404(AudioFile, id=audio_id, user=request.user)
    
    # We split tasks into pending and completed for the template
    pending_tasks = audio_file.todos.filter(is_done=False)
    completed_tasks = audio_file.todos.filter(is_done=True).order_by('-id') # Show newest completed first
        
    context = {
        'audio': audio_file,
        'pending_tasks': pending_tasks,
        'completed_tasks': completed_tasks,
        'active_page': 'todos' # 👈 To highlight the nav link
    }
    return render(request, 'core/to_do.html', context)

# ===================================================================
# 4. DEADLINES VIEW (Using ImportantPoint)
# ===================================================================
@login_required
def deadlines_view(request, audio_id):
    audio_file = get_object_or_404(AudioFile, id=audio_id, user=request.user)
    
    # Fetch ImportantPoint objects, which are the deadlines
    important_points = audio_file.important_points.all().order_by('id')
    has_google_token = SocialToken.objects.filter(account__user=request.user, account__provider='google').exists()
        
    context = {
        'audio': audio_file,
        'important_points': important_points,
        'active_page': 'deadlines', # 👈 To highlight the nav link
        'has_google_token': has_google_token
    }
    return render(request, 'core/important_deadlines.html', context)

# ===================================================================
# 5. EMAIL VIEW (Shows draft or "under construction")
# ===================================================================
@login_required
def email_view(request, audio_id):
    audio_file = get_object_or_404(AudioFile, id=audio_id, user=request.user)
    
    try:
        email_summary = audio_file.email
    except ObjectDoesNotExist:
        email_summary = None
    # Load draft if any
    from .models import EmailDraft
    email_draft = getattr(audio_file, 'email_draft', None)
    has_google_token = SocialToken.objects.filter(account__user=request.user, account__provider='google').exists()
        
    context = {
        'audio': audio_file,
        'email_summary': email_summary,
        'email_draft': email_draft,
        'has_google_token': has_google_token,
        'active_page': 'email' # 👈 To highlight the nav link
    }
    return render(request, 'core/email.html', context)

# ===================================================================
# 6. VIEW TO HANDLE CHECKBOX CLICKS (for To-Do page)
# ===================================================================
@require_POST
@login_required
def toggle_todo(request, todo_id):
    # Find the to-do item and make sure it belongs to the user
    todo = get_object_or_404(ToDoItem, id=todo_id)
    if todo.audio.user != request.user:
        # If not, return an error (or just redirect)
        return redirect('dashboard')
    
    # Flip its status
    todo.is_done = not todo.is_done
    todo.save()
    # Sync Keep note to reflect updated checklist
    try:
        sync_keep_note_for_audio(request, todo.audio)
    except Exception:
        pass
    
    # Send the user back to the to-do page
    return redirect('todo_view', audio_id=todo.audio.id)


# ===================================================================
# 7. NEW HELPER FUNCTION TO PARSE DATES
# ===================================================================
def parse_deadline_text(text):
    """
    Parses text like "by 6 PM today" or "before 12 PM tomorrow".
    Returns (start_datetime, end_datetime, is_all_day)
    """
    text_lower = text.lower()
    now = timezone.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    
    extracted_date = today  # Default to today
    is_all_day = True

    # 1. Find date keywords
    if "tomorrow" in text_lower:
        extracted_date = tomorrow
    elif "today" in text_lower:
        extracted_date = today
    else:
        # Try parsing a specific date (e.g., "Nov 10", "11/10/2025")
        try:
            # Use fuzzy_with_tokens to see if a date was *actually* parsed
            parsed_dt, tokens = parser.parse(text, fuzzy_with_tokens=True, default=now)
            # Check if any of the parsed tokens look like a date/time component
            if any(token.strip().lower() not in ['by', 'before', 'on', 'at', 'the'] for token in tokens):
                    extracted_date = parsed_dt.date()
        except (ValueError, OverflowError):
            pass  # No specific date found, stick with default (today)

    # 2. Find time keywords (e.g., "6 PM", "12 PM", "18:00")
    # This regex finds "6 PM", "6:30 PM", "18:00"
    time_match = re.search(r'(\d{1,2})\s*(?::\s*(\d{2}))?\s*(am|pm)', text_lower)
    extracted_time = None

    if time_match:
        is_all_day = False
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        meridiem = time_match.group(3)

        if meridiem == 'pm' and hour != 12:
            hour += 12
        if meridiem == 'am' and hour == 12:  # 12 AM is midnight
            hour = 0
        
        extracted_time = time(hour, minute)
    
    # 3. Combine date and time
    if is_all_day:
        start_iso = extracted_date.isoformat()
        end_iso = (extracted_date + timedelta(days=1)).isoformat() # All-day events are exclusive of end date
        return start_iso, end_iso, True
    else:
        # Get current timezone from Django settings
        local_tz = timezone.get_current_timezone()
        start_dt = datetime.combine(extracted_date, extracted_time)
        start_dt_aware = timezone.make_aware(start_dt, local_tz)
        
        # Make the event 1 hour long by default
        end_dt_aware = start_dt_aware + timedelta(hours=1)

        start_iso = start_dt_aware.isoformat()
        end_iso = end_dt_aware.isoformat()
        
        return start_iso, end_iso, False

# ===================================================================
# 8. NEW VIEW TO ADD EVENT TO GOOGLE CALENDAR
# ===================================================================
@require_POST
@login_required
def add_to_calendar(request, point_id):
    point = get_object_or_404(ImportantPoint, id=point_id)
    if point.audio.user != request.user:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    if point.is_added_to_calendar:
        return JsonResponse({'status': 'error', 'message': 'Already added'}, status=400)

    try:
        # 1. Get Google Token
        token = SocialToken.objects.get(account__user=request.user, account__provider='google')
    except SocialToken.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Google account not linked or token missing.'}, status=400)

    try:
        # 2. Parse the text to get date/time
        start_iso, end_iso, is_all_day = parse_deadline_text(point.text)
        
        # 3. Create Google Calendar event payload
        event_data = {
            'summary': point.text,
            'description': f"Task from AI Call Assistant.\nAudio: {point.audio.title}",
        }

        if is_all_day:
            event_data['start'] = {'date': start_iso}
            event_data['end'] = {'date': end_iso}
        else:
            event_data['start'] = {'dateTime': start_iso}
            event_data['end'] = {'dateTime': end_iso}

        # 4. Make API Call (force IPv4 to avoid NAT64/IPv6 issues on some networks)
        original_getaddrinfo = socket.getaddrinfo
        try:
            def ipv4_only_getaddrinfo(*args, **kwargs):
                results = original_getaddrinfo(*args, **kwargs)
                return [r for r in results if r[0] == socket.AF_INET]
            socket.getaddrinfo = ipv4_only_getaddrinfo

            headers = {
                'Authorization': f'Bearer {token.token}',
                'Content-Type': 'application/json'
            }
            
            # Post the event; if unauthorized, try refreshing the access token and retry
            calendar_url = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'
            response = requests.post(calendar_url, headers=headers, data=json.dumps(event_data))

            if response.status_code == 401:
                refresh_token = token.token_secret
                if not refresh_token:
                    return JsonResponse({'status': 'error', 'message': 'Google account not linked or token missing.'}, status=400)

                # Refresh the access token using OAuth2 refresh flow
                google_app = settings.SOCIALACCOUNT_PROVIDERS.get('google', {}).get('APP', {})
                client_id = google_app.get('client_id')
                client_secret = google_app.get('secret')

                # Fallback to DB SocialApp if settings-based APP is not provided
                if not client_id or not client_secret:
                    try:
                        site_id = getattr(settings, 'SITE_ID', None)
                        qs = SocialApp.objects.filter(provider='google')
                        if site_id:
                            qs = qs.filter(sites__id=site_id)
                        social_app = qs.first()
                        if social_app:
                            client_id = client_id or social_app.client_id
                            client_secret = client_secret or social_app.secret
                    except Exception:
                        pass

                if not client_id or not client_secret:
                    return JsonResponse({'status': 'error', 'message': 'OAuth client not configured.'}, status=500)

                token_resp = requests.post(
                    'https://oauth2.googleapis.com/token',
                    data={
                        'client_id': client_id,
                        'client_secret': client_secret,
                        'refresh_token': refresh_token,
                        'grant_type': 'refresh_token',
                    }
                )

                if token_resp.ok:
                    token_json = token_resp.json()
                    new_access = token_json.get('access_token')
                    expires_in = token_json.get('expires_in')
                    new_refresh = token_json.get('refresh_token')  # often absent on refresh

                    if not new_access:
                        return JsonResponse({'status': 'error', 'message': 'Failed to refresh Google access token.'}, status=500)

                    # Update stored token
                    token.token = new_access
                    if new_refresh:
                        token.token_secret = new_refresh
                    if expires_in:
                        token.expires_at = timezone.now() + timedelta(seconds=int(expires_in))
                    token.save()

                    # Retry calendar request with new access token
                    headers['Authorization'] = f'Bearer {token.token}'
                    response = requests.post(calendar_url, headers=headers, data=json.dumps(event_data))

                else:
                    # Refresh failed; ask user to re-connect Google
                    return JsonResponse({'status': 'error', 'message': 'Google session expired. Please sign in with Google again.'}, status=401)

            # Raise for any remaining errors
            response.raise_for_status()
        finally:
            socket.getaddrinfo = original_getaddrinfo

        # 5. Success: Update DB and return
        point.is_added_to_calendar = True
        point.save()
        return JsonResponse({'status': 'success', 'message': 'Event added to calendar.'})

    except requests.exceptions.HTTPError as e:
        # Handle API errors
        return JsonResponse({'status': 'error', 'message': f'Google API Error: {e.response.text}'}, status=e.response.status_code)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Error processing request: {str(e)}'}, status=500)


# ===================================================================
# 9. GOOGLE KEEP SYNC
# ===================================================================
def _get_google_bearer_token(user):
    token = SocialToken.objects.filter(account__user=user, account__provider='google').first()
    if not token:
        raise Exception('Google account not linked or token missing.')
    return token.token


def sync_keep_note_for_audio(request, audio: AudioFile):
    """
    Ensure a Keep note exists for this audio, with checklist items mirroring ToDoItem states.
    Since Keep API lacks content update endpoints, we delete and recreate the note.
    """
    bearer = _get_google_bearer_token(request.user)
    headers = {
        'Authorization': f'Bearer {bearer}',
        'Content-Type': 'application/json'
    }

    # Delete existing note if present
    if audio.keep_note_name:
        try:
            del_url = f'https://keep.googleapis.com/v1/{audio.keep_note_name}'
            requests.delete(del_url, headers=headers, timeout=20)
        except Exception:
            pass

    # Build list items from current todos
    list_items = []
    for t in audio.todos.all().order_by('id'):
        list_items.append({
            'text': {'text': t.text[:950]},
            'checked': bool(t.is_done)
        })

    note_payload = {
        'title': audio.title or f'Audio {audio.id}',
        'body': {
            'list': {
                'listItems': list_items
            }
        }
    }

    resp = requests.post('https://keep.googleapis.com/v1/notes', headers=headers, data=json.dumps(note_payload), timeout=30)
    if not resp.ok:
        raise Exception(f'Keep create failed: {resp.text}')
    note = resp.json()
    audio.keep_note_name = note.get('name')
    audio.save(update_fields=['keep_note_name'])


# ===================================================================
# 10. EMAIL DRAFT SAVE & SEND (GMAIL)
# ===================================================================
@require_POST
@login_required
def save_email_draft(request, audio_id):
    audio = get_object_or_404(AudioFile, id=audio_id, user=request.user)
    from .models import EmailDraft
    draft, _ = EmailDraft.objects.get_or_create(audio=audio)
    draft.to_name = request.POST.get('to_name') or None
    draft.to_email = request.POST.get('to_email') or None
    draft.subject = request.POST.get('subject') or ''
    draft.body = request.POST.get('body') or ''
    draft.is_needed = request.POST.get('is_needed') == 'on'
    draft.save()
    messages.success(request, 'Draft saved.')
    return redirect('email_view', audio_id=audio.id)


@require_POST
@login_required
def send_email_draft(request, audio_id):
    audio = get_object_or_404(AudioFile, id=audio_id, user=request.user)
    from .models import EmailDraft
    draft = getattr(audio, 'email_draft', None)
    if not draft or not draft.body or not draft.subject or not draft.to_email:
        messages.error(request, 'Please fill To, Subject and Body before sending.')
        return redirect('email_view', audio_id=audio.id)

    # Get Google token
    token_obj = SocialToken.objects.filter(account__user=request.user, account__provider='google').first()
    if not token_obj:
        messages.error(request, 'Google account not linked or token missing.')
        return redirect('email_view', audio_id=audio.id)

    # Build email
    em = EmailMessage()
    em['To'] = draft.to_email
    em['Subject'] = draft.subject
    em.set_content(draft.body)
    raw = base64.urlsafe_b64encode(em.as_bytes()).decode('utf-8')

    headers = {
        'Authorization': f'Bearer {token_obj.token}',
        'Content-Type': 'application/json'
    }
    send_url = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
    resp = requests.post(send_url, headers=headers, data=json.dumps({'raw': raw}), timeout=30)
    if resp.ok:
        messages.success(request, 'Email sent successfully.')
    else:
        messages.error(request, f'Failed to send email: {resp.text}')
    return redirect('email_view', audio_id=audio.id)