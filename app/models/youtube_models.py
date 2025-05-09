from pydantic import BaseModel

class GetYoutubeAuthUrlRequest(BaseModel):
    youtube_channel_id: str
    client_secret_filename: str # This will be the key for the R2 object

class GetYoutubeAuthUrlResponse(BaseModel):
    authorization_url: str 