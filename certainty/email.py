from datetime import datetime
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From
from certainty import BASE_URL

from_details = From(
    email=os.getenv("FROM_EMAIL"),
    name=os.getenv("FROM_NAME"),
)


def send_magic_link(email: str, magic_token: str) -> None:
    message = Mail(
        from_email=from_details,
        to_emails=email,
        subject="CERTainty Magic Link",
        html_content=f"""<p> Hello!</p>

        <p>We think you have requested a magic link to log in to Certainty. If you did not request this, please ignore this email.</p>

        <p>Your magic link is <a clicktracking=off href="{BASE_URL}/management/{magic_token}">{BASE_URL}/management/{magic_token}</a>.</p>
        
        <p>Many thanks!</p>
    """,
    )

    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        sg.send(message)
    except Exception as e:
        print(e.message)


def send_monitor_error(email: str, domain: str, uuid: str) -> None:
    message = Mail(
        from_email=from_details,
        to_emails=email,
        subject=f"SSL certificate error for {domain}!",
        html_content=f"""<p>Hello!</p>

        <p>This email serves as a notification we encountered an error checking SSL certificate for {domain}, which may indicate an issue with the certificate.</p>
        
        <p>You can view the monitor <a clicktracking=off href="{BASE_URL}/monitor/{uuid}">here</a>.</p>

        <p>Many thanks!</p>
        """,
    )

    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        sg.send(message)
    except Exception as e:
        print(e.message)


def send_monitor_expired(
    email: str, domain: str, uuid: str, expires_at: datetime
) -> None:
    message = Mail(
        from_email=from_details,
        to_emails=email,
        subject=f"SSL certificate for {domain} has expired!",
        html_content=f"""<p>Hello!</p>

        <p>This email serves as a notification that the SSL certificate for {domain} has expired, and become invalid on {expires_at}.</p>
        
        <p>You can view the monitor <a clicktracking=off href="{BASE_URL}/monitor/{uuid}">here</a>.</p>

        <p>Many thanks!</p>
        """,
    )

    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        sg.send(message)
    except Exception as e:
        print(e.message)


def send_monitor_expiring(
    email: str, domain: str, uuid: str, expires_at: datetime
) -> None:
    message = Mail(
        from_email=from_details,
        to_emails=email,
        subject=f"SSL certificate for {domain} is expiring soon",
        html_content=f"""<p>Hello!</p>

        <p>This email serves as a notification that the SSL certificate for {domain} is expiring soon, and will become invalid on {expires_at}.</p>
        
        <p>You can view the monitor <a clicktracking=off href="{BASE_URL}/monitor/{uuid}">here</a>.</p>

        <p>Many thanks!</p>
        """,
    )

    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        sg.send(message)
    except Exception as e:
        print(e.message)


def send_monitor_renewed(
    email: str, domain: str, uuid: str, expires_at: datetime
) -> None:
    message = Mail(
        from_email=from_details,
        to_emails=email,
        subject=f"SSL certificate for {domain} has been renewed",
        html_content=f"""<p>Hello!</p>

        <p>This email serves as a notification that the SSL certificate for {domain} is now functional, and is valid until {expires_at}.</p>
        
        <p>You can view the monitor <a clicktracking=off href="{BASE_URL}/monitor/{uuid}">here</a>.</p>

        <p>Many thanks!</p>
        """,
    )

    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        sg.send(message)
    except Exception as e:
        print(e.message)


def send_monitor_deleted(email: str, domain: str) -> None:
    message = Mail(
        from_email=from_details,
        to_emails=email,
        subject=f"SSL certificate monitor for {domain} has been deleted",
        html_content=f"""<p>Hello!</p>

        <p>This email serves as a notification that the SSL certificate monitor for {domain} has been deleted, and will no longer be checked.</p>

        <p>You are welcome to create a new monitor at any time at <a href="https://certainty.dev">https://certainty.dev</a>.</p>
        
        <p>Many thanks!</p>
        """,
    )

    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        sg.send(message)
    except Exception as e:
        print(e.message)
