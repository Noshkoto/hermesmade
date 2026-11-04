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
        plan = await run_in_threadpool(H.pack, body.get("profile") or None, title=body.get("title", ""),
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
        plan = await run_in_threadpool(H.pack, body.get("profile") or None, title=body.get("title", ""),
                                       tagline=body.get("tagline", ""), description=body.get("description", ""))
        res = await run_in_threadpool(H.upload, plan, str(body.get("handle", "")))
        return {k: v for k, v in res.items() if k != "manage_token"}
    except H.ShareError as e:
        _err(e)


@router.get("/mine")
async def mine():
    return H.my_shares()
