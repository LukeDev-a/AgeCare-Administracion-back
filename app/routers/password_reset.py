from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, EmailStr, Field

from app.deps import Db
from app.password_reset import request_reset, confirm_reset

router = APIRouter(tags=['Recuperación de contraseña'])


class ResetRequestIn(BaseModel):
    email: EmailStr


class ResetConfirmIn(BaseModel):
    token: str = Field(min_length=40, max_length=200)
    password: str = Field(min_length=8, max_length=128)


@router.post('/auth/password-reset/request', status_code=202)
async def request_password_reset(body: ResetRequestIn, request: Request, response: Response, db: Db):
    response.headers['Cache-Control'] = 'no-store'
    await request_reset(db, str(body.email), request)
    return {'message': 'Si el correo corresponde a una cuenta activa, recibirás un enlace para cambiar tu contraseña.'}


@router.post('/auth/password-reset/confirm')
async def confirm_password_reset(body: ResetConfirmIn, request: Request, response: Response, db: Db):
    response.headers['Cache-Control'] = 'no-store'
    await confirm_reset(db, body.token, body.password, request)
    return {'changed': True}
