import logging
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()
logging.basicConfig(level=logging.INFO)

from .database import DATABASE_URL, get_session, init_db
from .mailer import send_ticket_resolved_email
from .models import Asset, Ticket, User
from .security import decrypt_password, encrypt_password, verify_advance_token, verify_password
from .seed import seed
from .telegram import send_ticket_notification

app = FastAPI(title="Portal de Incidencias Meta")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev-secret-change-me"))
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")
TYPE_LABELS = {"bm": "Business Manager", "page": "Fan Page", "profile": "Perfil personal"}
TYPE_ICONS = {"bm": "ti-building-store", "page": "ti-brand-facebook", "profile": "ti-user-circle"}
templates.env.globals["type_label"] = lambda t: TYPE_LABELS.get(t, t)
templates.env.globals["asset_icon"] = lambda t: TYPE_ICONS.get(t, "ti-building-store")
templates.env.globals["asset_version"] = str(int(datetime.now(timezone.utc).timestamp()))


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
    if not user or not verify_password(password, user.password_encrypted):
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

    await send_ticket_notification(ticket, user.username, decrypt_password(user.password_encrypted))

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

    owners = {u.id: u for u in session.exec(select(User)).all()}

    def ticket_view(t: Ticket) -> dict:
        owner = owners.get(t.user_id)
        return {
            "id": t.id,
            "code": t.code,
            "client_name": t.client_name,
            "asset_label": t.asset_label,
            "asset_external_id": t.asset_external_id,
            "asset_type": t.asset_type,
            "status": t.status,
            "created_at": t.created_at,
            "email": owner.email if owner else None,
        }

    views = [ticket_view(t) for t in tickets]
    columns = {
        "open": [v for v in views if v["status"] == "open"],
        "progress": [v for v in views if v["status"] == "progress"],
        "done": [v for v in views if v["status"] == "done"],
    }

    monday_this_week = today - timedelta(days=today.weekday())
    monday_last_week = monday_this_week - timedelta(days=7)

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": user,
            "columns": columns,
            "stats": stats,
            "active_tab": "tickets",
            "default_date_from": monday_last_week.isoformat(),
            "default_date_to": today.isoformat(),
        },
    )


@app.post("/admin/tickets/{ticket_id}/status")
def admin_update_ticket_status(
    ticket_id: int,
    request: Request,
    status: str = Form(...),
    session: Session = Depends(get_session),
):
    user = get_current_user(request, session)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403)
    if status not in ("open", "progress", "done"):
        raise HTTPException(status_code=400)

    ticket = session.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404)

    ticket.status = status
    session.add(ticket)
    session.commit()
    return {"ok": True}


@app.post("/admin/tickets/{ticket_id}/notify")
async def admin_notify_ticket_resolved(
    ticket_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    user = get_current_user(request, session)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403)

    ticket = session.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404)

    owner = session.get(User, ticket.user_id)
    if not owner or not owner.email:
        raise HTTPException(status_code=400, detail="El cliente no tiene un email registrado.")

    await send_ticket_resolved_email(owner.email, owner.name, ticket.code)
    return {"ok": True}


@app.get("/t/advance/{token}")
def advance_ticket_via_link(token: str, request: Request, session: Session = Depends(get_session)):
    ticket_id = verify_advance_token(token)
    if ticket_id is None:
        return templates.TemplateResponse(
            "ticket_action.html",
            {
                "request": request,
                "is_error": True,
                "icon": "ti-alert-circle",
                "title": "Enlace inválido",
                "message": "Este enlace no es válido.",
            },
            status_code=400,
        )

    ticket = session.get(Ticket, ticket_id)
    if not ticket:
        return templates.TemplateResponse(
            "ticket_action.html",
            {
                "request": request,
                "is_error": True,
                "icon": "ti-alert-circle",
                "title": "Ticket no encontrado",
                "message": "No se encontró el ticket asociado a este enlace.",
            },
            status_code=404,
        )

    if ticket.status == "open":
        ticket.status = "progress"
        session.add(ticket)
        session.commit()
        message = f"El ticket {ticket.code} se movió a En proceso."
    elif ticket.status == "progress":
        message = f"El ticket {ticket.code} ya está En proceso."
    else:
        message = f"El ticket {ticket.code} ya está Resuelto."

    return templates.TemplateResponse(
        "ticket_action.html",
        {
            "request": request,
            "is_error": False,
            "icon": "ti-circle-check",
            "title": "Listo",
            "message": message,
        },
    )


def _usuarios_context(request: Request, user: User, session: Session, tipo: str, **extra):
    if tipo not in ("clientes", "administradores"):
        tipo = "clientes"
    want_admin = tipo == "administradores"
    rows = session.exec(select(User).where(User.is_admin == want_admin)).all()
    usuarios = [
        {
            "id": u.id,
            "name": u.name,
            "username": u.username,
            "password": decrypt_password(u.password_encrypted),
            "email": u.email or "",
            "assets": session.exec(select(Asset).where(Asset.owner_id == u.id)).all(),
        }
        for u in rows
    ]
    extra.setdefault("expand", None)
    return {
        "request": request,
        "user": user,
        "active_tab": "usuarios",
        "tipo": tipo,
        "usuarios": usuarios,
        **extra,
    }


@app.get("/admin/usuarios")
def admin_usuarios(
    request: Request,
    tipo: str = "clientes",
    expand: int | None = None,
    session: Session = Depends(get_session),
):
    user = get_current_user(request, session)
    if not user or not user.is_admin:
        return RedirectResponse("/login")
    return templates.TemplateResponse(
        "admin_usuarios.html", _usuarios_context(request, user, session, tipo, expand=expand)
    )


@app.post("/admin/usuarios")
def admin_usuarios_create(
    request: Request,
    tipo: str = Form(...),
    nombre: str = Form(...),
    cuenta: str = Form(...),
    password: str = Form(...),
    email: str = Form(""),
    session: Session = Depends(get_session),
):
    user = get_current_user(request, session)
    if not user or not user.is_admin:
        return RedirectResponse("/login", status_code=303)

    initials = "".join(part[0] for part in nombre.split()[:2]).upper() or "US"
    nuevo = User(
        username=cuenta,
        password_encrypted=encrypt_password(password),
        name=nombre,
        initials=initials,
        is_admin=(tipo == "administradores"),
        email=email.strip() or None,
    )
    session.add(nuevo)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return templates.TemplateResponse(
            "admin_usuarios.html",
            _usuarios_context(
                request, user, session, tipo,
                error="Esa cuenta ya está en uso.", form_nombre=nombre, form_cuenta=cuenta, form_email=email,
            ),
            status_code=400,
        )

    return RedirectResponse(f"/admin/usuarios?tipo={tipo}", status_code=303)


@app.post("/admin/usuarios/{user_id}/estructuras")
def admin_usuarios_add_estructura(
    user_id: int,
    request: Request,
    tipo: str = Form(...),
    nombre: str = Form(...),
    activo: str = Form(...),
    codigo: str = Form(...),
    session: Session = Depends(get_session),
):
    admin_user = get_current_user(request, session)
    if not admin_user or not admin_user.is_admin:
        return RedirectResponse("/login", status_code=303)

    target = session.get(User, user_id)
    if not target:
        return RedirectResponse(f"/admin/usuarios?tipo={tipo}", status_code=303)

    asset = Asset(
        external_id=codigo,
        label=nombre,
        type=activo,
        icon=TYPE_ICONS.get(activo, "ti-building-store"),
        owner_id=target.id,
    )
    session.add(asset)
    session.commit()

    return RedirectResponse(f"/admin/usuarios?tipo={tipo}&expand={user_id}", status_code=303)


@app.post("/admin/usuarios/{user_id}/estructuras/{asset_id}/edit")
def admin_usuarios_edit_estructura(
    user_id: int,
    asset_id: int,
    request: Request,
    tipo: str = Form(...),
    nombre: str = Form(...),
    activo: str = Form(...),
    codigo: str = Form(...),
    session: Session = Depends(get_session),
):
    admin_user = get_current_user(request, session)
    if not admin_user or not admin_user.is_admin:
        return RedirectResponse("/login", status_code=303)

    asset = session.get(Asset, asset_id)
    if asset and asset.owner_id == user_id:
        asset.label = nombre
        asset.type = activo
        asset.external_id = codigo
        asset.icon = TYPE_ICONS.get(activo, "ti-building-store")
        session.add(asset)
        session.commit()

    return RedirectResponse(f"/admin/usuarios?tipo={tipo}&expand={user_id}", status_code=303)


@app.post("/admin/usuarios/{user_id}/estructuras/{asset_id}/delete")
def admin_usuarios_delete_estructura(
    user_id: int,
    asset_id: int,
    request: Request,
    tipo: str = Form(...),
    session: Session = Depends(get_session),
):
    admin_user = get_current_user(request, session)
    if not admin_user or not admin_user.is_admin:
        return RedirectResponse("/login", status_code=303)

    asset = session.get(Asset, asset_id)
    if asset and asset.owner_id == user_id:
        session.delete(asset)
        session.commit()

    return RedirectResponse(f"/admin/usuarios?tipo={tipo}&expand={user_id}", status_code=303)


@app.post("/admin/usuarios/{user_id}/edit")
def admin_usuarios_edit(
    user_id: int,
    request: Request,
    tipo: str = Form(...),
    nombre: str = Form(...),
    cuenta: str = Form(...),
    password: str = Form(...),
    email: str = Form(""),
    session: Session = Depends(get_session),
):
    admin_user = get_current_user(request, session)
    if not admin_user or not admin_user.is_admin:
        return RedirectResponse("/login", status_code=303)

    target = session.get(User, user_id)
    if not target:
        return RedirectResponse(f"/admin/usuarios?tipo={tipo}", status_code=303)

    target.name = nombre
    target.username = cuenta
    target.password_encrypted = encrypt_password(password)
    target.email = email.strip() or None
    target.initials = "".join(part[0] for part in nombre.split()[:2]).upper() or "US"
    session.add(target)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return templates.TemplateResponse(
            "admin_usuarios.html",
            _usuarios_context(request, admin_user, session, tipo, error="Esa cuenta ya está en uso."),
            status_code=400,
        )

    return RedirectResponse(f"/admin/usuarios?tipo={tipo}", status_code=303)
