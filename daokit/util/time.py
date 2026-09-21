from datetime import datetime
from zoneinfo import ZoneInfo


TimeZoneUTC = ZoneInfo("UTC")


def now_tz(tz: ZoneInfo = TimeZoneUTC) -> datetime:
    return datetime.now(tz=tz)

def now_utc() -> datetime:
    # 项目中统一使用 UTC 时间
    return now_tz(tz=TimeZoneUTC)