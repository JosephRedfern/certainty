import datetime
import os
import logging

from typing import Annotated
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from redis import Redis
from starsessions import CookieStore, SessionAutoloadMiddleware, SessionMiddleware
from tortoise import Tortoise
from dotenv import load_dotenv
from rq import Queue
from rq_scheduler import Scheduler
import validators

logger = logging.getLogger(__name__)

# we need to do this before importing anything else as we other end up with circular imports. not ideal.
load_dotenv(".env")
BASE_URL = os.getenv("BASE_URL")


from certainty.monitor import check_certificates_sync

from certainty.email import send_magic_link


# We need to initialize the models before defining marshalling classes
Tortoise.init_models(["certainty.models"], "models")

from fastapi import Depends, FastAPI, Request, Form, Response
from tortoise.contrib.fastapi import register_tortoise

from certainty.marshalling import (
    CertificateMonitorPostRequest,
    CertificateMonitorResponse,
)

from certainty.models import CertificateMonitor, MagicLink

from certainty.monitor import (
    create_certificate_monitor,
    get_certificate_monitor,
    refresh_certificate_monitor,
)


app = FastAPI()
redis_conn = Redis(host=os.getenv("REDIS_HOST"), port=6379)
q = Queue("certainty", connection=redis_conn)
scheduler = Scheduler(
    "certainty", connection=redis_conn
)  # Get a scheduler for the "foo" queue


app.mount("/static", StaticFiles(directory="certainty/static"), name="static")
templates = Jinja2Templates(directory="certainty/templates")

app.add_middleware(SessionAutoloadMiddleware)
app.add_middleware(
    SessionMiddleware, store=CookieStore(secret_key="topsecretsessionkey")
)

register_tortoise(
    app,
    db_url=os.getenv("DB_URL"),
    modules={"models": ["certainty.models"]},
    generate_schemas=True,
    add_exception_handlers=True,
)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        request, "index.html", context={"email": request.session.get("email")}
    )


@app.post("/", response_class=HTMLResponse)
async def create_monitor(
    domain: Annotated[str, Form()],
    email: Annotated[str, Form()],
    warning_days: Annotated[int, Form()],
    request: Request,
):
    error = None

    # Check if domain looks like a domain
    if not validators.domain(domain):
        error = "Please provide a valid domain"
    elif not validators.email(email):
        error = "Please provide a valid email"
    elif validators.between(warning_days, min=1, max=365):
        error = "Please provide a valid number of warning days"

    if error:
        return templates.TemplateResponse(
            request,
            "index.html",
            context={"error": error, "email": request.session.get("email")},
        )

    # Create monitor
    monitor = await create_certificate_monitor(domain, email, warning_days)

    # Refresh monitor
    monitor = await refresh_certificate_monitor(monitor.uuid)

    request.session["created_uuid"] = str(monitor.uuid)

    # Redirect to the monitor page with a 303 status code
    return RedirectResponse(url=f"/monitor/{monitor.uuid}", status_code=303)


@app.get("/monitor/{monitor_id}", response_class=HTMLResponse)
async def get_monitor(request: Request, monitor_id: str):
    monitor = await get_certificate_monitor(monitor_id)

    if monitor.email != request.session.get("email") and str(
        monitor.uuid
    ) != request.session.get("created_uuid"):
        return RedirectResponse(url="/")

    return templates.TemplateResponse(
        request,
        "monitor.html",
        {
            "monitor": monitor,
            "email": request.session.get("email"),
            "user_created_this_monitor": request.session.get("created_uuid")
            == str(monitor.uuid),
        },
    )


@app.get("/monitor/{monitor_id}/prometheus")
async def get_prometheus_metrics(request: Request, monitor_id: str):
    monitor = await get_certificate_monitor(monitor_id)

    if not monitor:
        return PlainTextResponse("Monitor not found", status_code=404)

    metrics = []

    # Metric for time until expiration
    metrics.append(
        "# HELP cert_seconds_until_expiry The number of seconds until the certificate expires"
    )
    metrics.append("# TYPE cert_seconds_until_expiry gauge")
    if monitor.not_after:
        seconds_until_expiry = (
            monitor.not_after - datetime.datetime.now(tz=datetime.timezone.utc)
        ).total_seconds()
        metrics.append(
            f'cert_seconds_until_expiry{{domain="{monitor.domain}"}} {seconds_until_expiry}'
        )

    # Metric for last check timestamp
    metrics.append(
        "# HELP cert_last_checked_timestamp The timestamp of the last certificate check"
    )
    metrics.append("# TYPE cert_last_checked_timestamp gauge")
    if monitor.checked_at:
        last_checked = monitor.checked_at.timestamp()
        metrics.append(
            f'cert_last_checked_timestamp{{domain="{monitor.domain}"}} {last_checked}'
        )

    # Metric for notBefore
    metrics.append(
        "# HELP cert_not_before The timestamp of the certificate notBefore date"
    )
    metrics.append("# TYPE cert_not_before gauge")
    if monitor.not_before:
        not_before = monitor.not_before.timestamp()
        metrics.append(f'cert_not_before{{domain="{monitor.domain}"}} {not_before}')

    # Metric for notAfter
    metrics.append(
        "# HELP cert_not_after The timestamp of the certificate notAfter date"
    )
    metrics.append("# TYPE cert_not_after gauge")
    if monitor.not_after:
        not_after = monitor.not_after.timestamp()
        metrics.append(f'cert_not_after{{domain="{monitor.domain}"}} {not_after}')

    # Metric for monitor state
    metrics.append(
        "# HELP cert_monitor_state The state of the certificate monitor (0=UNKNOWN, 1=OK, 2=EXPIRED, 3=EXPIRING, 4=ERROR)"
    )
    metrics.append("# TYPE cert_monitor_state gauge")
    state_value = {"UNKNOWN": 0, "OK": 1, "EXPIRED": 2, "EXPIRING": 3, "ERROR": 4}[
        monitor.state
    ]
    metrics.append(f'cert_monitor_state{{domain="{monitor.domain}"}} {state_value}')

    return PlainTextResponse("\n".join(metrics))


@app.post("/monitor/{monitor_id}/refresh")
async def refresh_monitor(request: Request, monitor_id: str):
    monitor = await get_certificate_monitor(monitor_id)

    if (
        monitor.email != request.session.get("email")
        and request.session.get("created_uuid") != monitor_id
    ):
        return RedirectResponse(url="/", status_code=303)

    current_time = datetime.datetime.now(tz=datetime.timezone.utc)
    if (
        monitor.checked_at is None
        or (current_time - monitor.checked_at).total_seconds() > 5
    ):
        monitor = await refresh_certificate_monitor(monitor_id)
    else:
        logger.info(
            f"Skipping refresh for monitor {monitor_id} as it was recently checked"
        )

    return RedirectResponse(url=f"/monitor/{monitor_id}", status_code=303)


@app.post("/monitor/{monitor_id}/delete")
async def delete_monitor(request: Request, monitor_id: str):
    monitor = await get_certificate_monitor(monitor_id)

    if (
        monitor.email != request.session.get("email")
        and request.session.get("created_uuid") != monitor_id
    ):
        return RedirectResponse(url="/", status_code=303)

    await monitor.delete()

    if request.session.get("email"):
        return RedirectResponse(url="/management", status_code=303)
    else:
        return RedirectResponse(url="/", status_code=303)


@app.get("/management", response_class=HTMLResponse)
async def management_get(request: Request):
    if (email := request.session.get("email")) is not None:
        monitors = await CertificateMonitor.filter(email=email)

        return templates.TemplateResponse(
            request,
            "monitors.html",
            context={"monitors": monitors, "email": request.session.get("email")},
        )
    else:
        return templates.TemplateResponse(request, "management.html")


@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")


@app.post("/management", response_class=HTMLResponse)
async def management_post(email: Annotated[str, Form()], request: Request):
    ml = await MagicLink.create(email=email)

    q.enqueue(send_magic_link, email, ml.token)

    return templates.TemplateResponse(
        request,
        "management.html",
        context={"link": ml, email: request.session.get("email")},
    )


@app.get("/management/{magic_link}", response_class=HTMLResponse)
async def management_magic_link_get(
    request: Request, magic_link: str, response: Response
):
    ml = await MagicLink.get(token=magic_link)

    if ml.used_at is None:
        ml.used_at = datetime.datetime.now(tz=datetime.timezone.utc)
        await ml.save(update_fields=["used_at"])

        request.session["email"] = ml.email

        return RedirectResponse(url="/management")
    else:
        return templates.TemplateResponse(
            request,
            "management.html",
            context={"error": "Invalid or expired magic link"},
            status=403,
        )


@app.post("/api/monitors")
async def monitor(certificate_monitor_request: CertificateMonitorPostRequest):
    certificate_monitor = await create_certificate_monitor(
        certificate_monitor_request.domain,
        certificate_monitor_request.email,
        certificate_monitor_request.warning_days,
    )

    return await refresh_certificate_monitor(certificate_monitor.uuid)


@app.get("/api/monitors/{monitor_id}")
async def get_monitor_api(monitor_id: str) -> CertificateMonitorResponse:
    monitor = await get_certificate_monitor(monitor_id)

    return monitor


@app.get("/api/monitors/{monitor_id}/refresh")
async def get_certificate_api(monitor_id: str) -> CertificateMonitorResponse:
    return await refresh_certificate_monitor(monitor_id)


@app.on_event("startup")
async def app_startup():
    for job in scheduler.get_jobs():
        if job.func_name == "certainty.monitor.check_certificates_sync":
            logger.debug(f"Cancelling old check certififcates scheduled job: {job}")
            scheduler.cancel(job)

    scheduler.schedule(
        scheduled_time=datetime.datetime.now(tz=datetime.UTC),
        func=check_certificates_sync,
        interval=10,
        repeat=None,
        result_ttl=60,
    )
