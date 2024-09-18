import datetime
import uuid
from tortoise.models import Model
from tortoise import fields
import enum
import secrets


class MonitorState(str, enum.Enum):
    UNKNOWN = "UNKNOWN"
    OK = "OK"
    EXPIRED = "EXPIRED"
    EXPIRING = "EXPIRING"
    ERROR = "ERROR"


class CertificateMonitor(Model):
    id = fields.IntField(pk=True)
    uuid = fields.UUIDField(default=uuid.uuid4)
    domain = fields.CharField(max_length=255, validators=[lambda x: len(x.strip()) > 0])
    email = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)
    checked_at = fields.DatetimeField(null=True)
    warning_days = fields.IntField(default=7)
    enabled = fields.BooleanField(default=True)
    state = fields.CharEnumField(enum_type=MonitorState, default=MonitorState.UNKNOWN)

    serial = fields.CharField(max_length=255, null=True)
    not_before = fields.DatetimeField(null=True)
    not_after = fields.DatetimeField(null=True)

    def time_remaining(self) -> datetime.timedelta:
        if self.not_after is not None:
            return self.not_after - datetime.datetime.now(tz=datetime.timezone.utc)

    class PydanticMeta:
        computed = ("time_remaining",)


class MagicLink(Model):
    id = fields.IntField(pk=True)
    email = fields.CharField(max_length=255)
    token = fields.CharField(max_length=255, default=lambda: secrets.token_urlsafe(32))
    created_at = fields.DatetimeField(auto_now_add=True)
    used_at = fields.DatetimeField(null=True)
