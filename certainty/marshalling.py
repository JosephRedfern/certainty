from certainty.models import CertificateMonitor
from pydantic import BaseModel
from tortoise.contrib.pydantic import pydantic_model_creator

CertificateMonitorResponse = pydantic_model_creator(CertificateMonitor)
CertificateMonitorPostRequest = pydantic_model_creator(
    CertificateMonitor,
    name="CertificateMonitorPostRequest",
    include=["domain", "email", "warning_days"],
)
