import os
import requests
from datetime import timedelta, timezone
from typing import Dict
from zoneinfo import ZoneInfo

from app.schemas.meeting import MeetingCreateRequest
from sqlalchemy.orm import Session
from datetime import datetime
from app.models.upcoming_meeting import UpcomingMeeting
from app.core.global_case import global_case


TENANT_ID = os.getenv("MS_TENANT_ID")
CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")

TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"

# Service account organizer (assign special meeting policy to this user)
organizer_email = os.getenv("ORGANIZER_EMAIL")


def _get_access_token() -> str:
    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        raise RuntimeError("Microsoft Graph credentials are not set in environment variables")

    token_url = TOKEN_URL_TEMPLATE.format(tenant_id=TENANT_ID)

    token_data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
        "scope": GRAPH_SCOPE,
    }

    response = requests.post(token_url, data=token_data, timeout=15)
    response.raise_for_status()

    return response.json()["access_token"]


def create_teams_meeting(data: MeetingCreateRequest,db:Session) -> Dict:
    access_token = _get_access_token()

    # ------------------------------------------------------------------
    # 1) Convert frontend time → UTC
    # ------------------------------------------------------------------
    if data.start_time.tzinfo is None:
        local_tz = ZoneInfo(data.timezone)
        start_dt_local = data.start_time.replace(tzinfo=local_tz)
    else:
        start_dt_local = data.start_time

    start_dt_utc = start_dt_local.astimezone(timezone.utc)
    end_dt_utc = start_dt_utc + timedelta(minutes=data.duration_minutes)

    start_iso = start_dt_utc.strftime("%Y-%m-%dT%H:%M:%S")
    end_iso = end_dt_utc.strftime("%Y-%m-%dT%H:%M:%S")

    # ------------------------------------------------------------------
    # 2) Build attendees from frontend
    # ------------------------------------------------------------------
    attendees = [
        {
            "emailAddress": {"address": email},
            "type": "required",
        }
        for email in data.participant_emails
    ]

    # ------------------------------------------------------------------
    # 3) Graph API payload
    # Lobby bypass handled via organizer's Teams meeting policy
    # ------------------------------------------------------------------
    payload = {
        "subject": data.meeting_title,
        "body": {
            "contentType": "HTML",
            "content": data.meeting_body,
        },
        "start": {
            "dateTime": start_iso,
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": end_iso,
            "timeZone": "UTC",
        },
        "location": {
            "displayName": "Microsoft Teams Meeting"
        },
        "attendees": attendees,
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # ------------------------------------------------------------------
    # 4) Create event using service account organizer
    # ------------------------------------------------------------------
    create_event_url = f"https://graph.microsoft.com/v1.0/users/{organizer_email}/events"

    response = requests.post(
        create_event_url,
        headers=headers,
        json=payload,
        timeout=20,
    )

    response.raise_for_status()

    try:
        graph_json = response.json()
    except ValueError:
        graph_json = {"raw": response.text}

    # ------------------------------------------------------------------
    # 5) Extract join URL
    # ------------------------------------------------------------------
    join_url = graph_json.get("onlineMeeting", {}).get("joinUrl")
    event_id = graph_json.get("id")

    meeting = UpcomingMeeting(
        case_id=data.case_id,
        meeting_title=data.meeting_title,
        graph_event_id=event_id,
        subject=str(data.case_id),
        meeting_body=data.meeting_body,
        join_url=join_url,
        start_time_utc=start_dt_utc,
        end_time_utc=end_dt_utc,
        timezone=data.timezone,
        participants=data.participant_emails,
        status="scheduled",
    )

    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return {
        "status_code": response.status_code,
        "graph_response": graph_json,
        "join_url": join_url,
        "event_id": event_id,
        "start_time_utc": start_dt_utc.isoformat(),
        "end_time_utc": end_dt_utc.isoformat(),
    }
    
def join_meeting_service(meeting_id: int, db: Session):

    meeting = (
        db.query(UpcomingMeeting)
        .filter(UpcomingMeeting.id == meeting_id)
        .first()
    )

    if not meeting:
        return None

    # -------------------------
    # Set global values
    # -------------------------
    global_case.case_id = meeting.case_id

    payload = {
        "JoinUrl": meeting.join_url
    }

    response = requests.post(
        "https://prashanttest01.duckdns.org:9441/joinCall",
        json=payload,
        timeout=15
    )

    response.raise_for_status()

    # -------------------------
    # Update DB
    # -------------------------
    meeting.bot_should_join = True
    meeting.bot_joined = True
    meeting.bot_joined_at = datetime.utcnow()
    meeting.status = "live"

    db.commit()

    return meeting