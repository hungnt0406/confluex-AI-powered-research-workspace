import asyncio
from backend.db.session import async_session_maker
from backend.db.models import User
from backend.security import hash_password
from backend.services.credits import credit

async def main():
    async with async_session_maker() as session:
        user = User(email="test12345@example.com", hashed_password=hash_password("password"))
        session.add(user)
        try:
            await session.flush()
            print(f"User ID: {user.id}")
            await credit(
                session,
                user_id=user.id,
                delta=100,
                kind="grant",
                metadata={"reason": "signup_bonus"},
            )
            await session.commit()
            print("Success")
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(main())
