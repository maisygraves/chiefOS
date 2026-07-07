from apscheduler.schedulers.background import BackgroundScheduler
from pywebpush import webpush, WebPushException
import os
from memory.longterm import get_settings

scheduler = BackgroundScheduler()
scheduler.start()

def send_push(subscription_info: dict, message: str):
    try:
        webpush(
            subscription_info=subscription_info,
            data=message,
            vapid_private_key=os.getenv("VAPID_PRIVATE_KEY"),
            vapid_claims={"sub": f"mailto:{os.getenv('VAPID_EMAIL')}"}
        )
    except WebPushException as ex:
        print("WebPush Error:", repr(ex))

def notify_morning():
    print("Sending morning notification...")

def notify_midday():
    print("Sending midday notification...")

def notify_evening():
    print("Sending evening notification...")

def setup_notifications():
    scheduler.remove_all_jobs()
    settings = get_settings()
    
    m_time = settings.get("morning_log_time", "08:00").split(":")
    md_time = settings.get("midday_log_time", "13:00").split(":")
    e_time = settings.get("evening_log_time", "20:00").split(":")
    
    scheduler.add_job(notify_morning, 'cron', hour=int(m_time[0]), minute=int(m_time[1]), id="morning_job")
    scheduler.add_job(notify_midday, 'cron', hour=int(md_time[0]), minute=int(md_time[1]), id="midday_job")
    scheduler.add_job(notify_evening, 'cron', hour=int(e_time[0]), minute=int(e_time[1]), id="evening_job")

# Initialize jobs on load
setup_notifications()
