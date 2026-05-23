import orjson
from redis.asyncio import Redis
from pydantic import BaseModel


async def publish(redis: Redis, channel: str, payload: BaseModel) -> int:
    """Publishes a payload to a Redis pub/sub channel.
    Returns the number of subscribers that received the message
    (0 if no one is listening — useful for observability)."""
    body = orjson.dumps(payload.model_dump(mode="json"))
    return await redis.publish(channel, body)
