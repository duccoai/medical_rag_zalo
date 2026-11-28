from pydantic import BaseModel, ConfigDict


class ZaloSender(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str


class ZaloMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    msg_id: str | None = None
    text: str | None = None


class ZaloWebhookEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    app_id: str | None = None
    event_name: str
    timestamp: str | int | None = None
    sender: ZaloSender | None = None
    recipient: ZaloSender | None = None
    message: ZaloMessage | None = None
