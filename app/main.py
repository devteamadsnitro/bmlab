import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()
logging.basicConfig(level=logging.INFO)

from .database import DATABASE_URL, get_session, init_db
from .models import Asset, Ticket, User
from .security import verify_password
from .seed import seed
from .telegram import send_ticket_notification

app = FastAPI(title="Portal de Incidencias Meta")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev-secret-change-me"))
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")
TYPE_LABELS = {"bm": "Business Manager", "page": "Fan Page", "profile": "Perfil personal"}
templates.env.globals["type_label"] = lambda t: TYPE_LABELS.get(t, t)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    seed()
    telegram_vars = sorted(k for k in os.environ if "TELEGRAM" in k.upper())
    logging.getLogger(__name__).info("Env vars matching TELEGRAM: %s", telegram_vars)
    logging.getLogger(__name__).info("DATABASE_URL scheme: %s", DATABASE_URL.split("://")[0])
    logging.getLogger(__name__).info("Total env vars visible to process: %d", len(os.environ))


def get_current_user(request: Request, session: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return session.get(User, user_id)


def next_ticket_code(session: Session) -> str:
    max_num = 0
    for code in session.exec(select(Ticket.code)):
        try:
            max_num = max(max_num, int(code.split("-")[1]))
        except (IndexError, ValueError):
            continue
    return f"INC-{max_num + 1:04d}"


@app.get("/")
def index(request: Request, session: Session = Depends(get_session)):
    user = get_current_user(request, session)
    if not user:
        return RedirectResponse("/login")
    return RedirectResponse("/admin" if user.is_admin else "/report")


@app.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    user = session.exec(select(User).where(User.username == username)).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Usuario o contraseña incorrectos."},
            status_code=401,
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/admin" if user.is_admin else "/report", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/report")
def report(request: Request, session: Session = Depends(get_session)):
    user = get_current_user(request, session)
    if not user:
        return RedirectResponse("/login")
    if user.is_admin:
        return RedirectResponse("/admin")
    assets = session.exec(select(Asset).where(Asset.owner_id == user.id)).all()
    return templates.TemplateResponse("report.html", {"request": request, "user": user, "assets": assets})


@app.post("/tickets")
async def create_ticket(
    request: Request,
    asset_id: str = Form(...),
    session: Session = Depends(get_session),
):
    user = get_current_user(request, session)
    if not user or user.is_admin:
        return RedirectResponse("/login", status_code=303)

    asset = session.exec(
        select(Asset).where(Asset.owner_id == user.id, Asset.external_id == asset_id)
    ).first()
    if not asset:
        return RedirectResponse("/report", status_code=303)

    ticket = Ticket(
        code=next_ticket_code(session),
        client_name=user.name,
        asset_external_id=asset.external_id,
        asset_label=asset.label,
        asset_type=asset.type,
        status="open",
        user_id=user.id,
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    await send_ticket_notification(ticket)

    return templates.TemplateResponse("success.html", {"request": request, "user": user, "ticket": ticket})


@app.get("/admin")
def admin(request: Request, session: Session = Depends(get_session)):
    user = get_current_user(request, session)
    if not user or not user.is_admin:
        return RedirectResponse("/login")

    tickets = session.exec(select(Ticket).order_by(Ticket.created_at.desc())).all()
    today = datetime.now(timezone.utc).date()
    stats = {
        "open": sum(1 for t in tickets if t.status == "open"),
        "bm": sum(1 for t in tickets if t.asset_type == "bm" and t.status != "done"),
        "today": sum(1 for t in tickets if t.created_at.date() == today),
    }
    return templates.TemplateResponse(
        "admin.html", {"request": request, "user": user, "tickets": tickets, "stats": stats}
    )
