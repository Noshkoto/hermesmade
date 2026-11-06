"""Backend for the hermesmade desktop page: /api/plugins/hermesmade/*.
Thin wrapper over hermesmade_share; every install and upload still needs the
user's explicit click in the desktop confirm screen."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

_PKG = Path(__file__).resolve().parent.parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))
import hermesmade_share as H  # noqa: E402

router = APIRouter()


def _err(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


@router.get("/preview")
async def preview_q(bot: str = ""):
    """``?bot=<id or link>``: a pasted link's slashes survive a query string, not a path segment."""
    try:
        return await run_in_threadpool(H.preview, bot)
    except H.ShareError as e:
        _err(e)


@router.get("/preview/{bot}")
async def preview(bot: str):
    try:
        return await run_in_threadpool(H.preview, bot)
    except H.ShareError as e:
        _err(e)


@router.post("/install")
async def install(body: dict):
    try:
        return await run_in_threadpool(H.install, str(body.get("bot", "")), name=(body.get("name") or None))
    except H.ShareError as e:
        _err(e)
    except Exception as e:  # installer errors (DistributionError etc.) carry useful text
        _err(e)


@router.get("/profiles")
async def profiles():
    from hermes_cli import profiles as P
    rows = await run_in_threadpool(P.list_profiles, lazy_skill_count=True)
    return {"profiles": [{"name": r.name, "title": r.bot_title or r.display_name or r.name} for r in rows]}


@router.post("/pack")
async def pack(body: dict):
    try:
        plan = await run_in_threadpool(H.pack, (body.get("bot_profile") or body.get("profile")) or None, title=body.get("title", ""),
                                       tagline=body.get("tagline", ""), description=body.get("description", ""))
        plan.pop("archive_bytes", None)
        return plan
    except H.ShareError as e:
        _err(e)


@router.post("/share")
async def share(body: dict):
    """Re-packs from the same inputs (so what uploads is what was just previewed
    from current files), then uploads."""
    try:
        plan = await run_in_threadpool(H.pack, (body.get("bot_profile") or body.get("profile")) or None, title=body.get("title", ""),
                                       tagline=body.get("tagline", ""), description=body.get("description", ""))
        res = await run_in_threadpool(H.upload, plan, str(body.get("handle", "")))
        return {k: v for k, v in res.items() if k != "manage_token"}
    except H.ShareError as e:
        _err(e)


@router.get("/mine")
async def mine():
    return H.my_shares()


# ---------------------------------------------------- Grok Bot migration --
def _grok(fn, *a, **kw):
    import hermesmade_migrate as G
    try:
        return fn(G)(*a, **kw)
    except G.MigrateError as e:
        _err(e)


@router.get("/grok/status")
async def grok_status():
    import hermesmade_migrate as G
    ok = await run_in_threadpool(G.importer_installed)
    return {"importer": ok, "install_hint": G.INSTALL_HINT,
            "prompt": (await run_in_threadpool(G.export_prompt)) if ok else "",
            "open_url": "https://x.ai/bot/link/v1/open"}


@router.post("/grok/install-importer")
async def grok_install_importer():
    """Runs only from the user's click on "Install importer" in the desktop page."""
    await run_in_threadpool(_grok, lambda G: G.install_importer)
    return await grok_status()


@router.get("/grok/downloads")
async def grok_downloads():
    return {"files": await run_in_threadpool(_grok, lambda G: G.find_downloads)}


@router.post("/grok/preview")
async def grok_preview(body: dict):
    return await run_in_threadpool(_grok, lambda G: G.preview, texts=[str(body.get("text") or "")] if body.get("text") else None,
                                   files=list(body.get("files") or []) or None)


@router.post("/grok/migrate")
async def grok_migrate(body: dict):
    out = await run_in_threadpool(
        _grok, lambda G: G.migrate, texts=[str(body.get("text") or "")] if body.get("text") else None,
        files=list(body.get("files") or []) or None, only=list(body.get("only") or []) or None,
        names=dict(body.get("names") or {}), activate_routines=False)
    return out
