"""
Seed script for initial data.
Run with: python -m app.seeds.seed_data
"""
import asyncio
import uuid

from sqlalchemy import select

from app.database.session import async_session_factory
from app.models.plan import Plan
from app.models.genre import Genre
from app.models.category import Category
from app.models.video import Video
from app.models.user import User, UserRole
from app.auth.hashing import hash_password


async def seed():
    async with async_session_factory() as session:
        # Check if data already exists
        result = await session.execute(select(Plan))
        if result.scalars().first():
            print("Data already seeded. Skipping.")
            return

        # Create Plans
        plans = [
            Plan(id=uuid.uuid4(), name="Basic", description="Acesso básico ao catálogo", price=9.90),
            Plan(id=uuid.uuid4(), name="Standard", description="Acesso completo com qualidade HD", price=29.90),
            Plan(id=uuid.uuid4(), name="Premium", description="Acesso completo com qualidade 4K e múltiplas telas", price=49.90),
        ]
        for plan in plans:
            session.add(plan)

        # Create Genres
        genres = [
            Genre(id=uuid.uuid4(), name="Science Fiction"),
            Genre(id=uuid.uuid4(), name="Drama"),
            Genre(id=uuid.uuid4(), name="Comedy"),
            Genre(id=uuid.uuid4(), name="Action"),
        ]
        for genre in genres:
            session.add(genre)

        # Create Categories
        categories = [
            Category(id=uuid.uuid4(), name="Documentary"),
            Category(id=uuid.uuid4(), name="Short Film"),
            Category(id=uuid.uuid4(), name="Series"),
            Category(id=uuid.uuid4(), name="Feature Film"),
        ]
        for category in categories:
            session.add(category)

        await session.flush()

        # Create Videos
        videos_data = [
            {
                "title": "The Future of AI",
                "description": "A documentary exploring artificial intelligence advancements.",
                "url": "https://streaming.example.com/videos/future-of-ai",
                "duration_seconds": 5400,
                "genres": [genres[0]],
                "categories": [categories[0]],
            },
            {
                "title": "Lost in Time",
                "description": "A dramatic series about time travelers.",
                "url": "https://streaming.example.com/videos/lost-in-time",
                "duration_seconds": 3600,
                "genres": [genres[0], genres[1]],
                "categories": [categories[2]],
            },
            {
                "title": "Comedy Night Live",
                "description": "Stand-up comedy special featuring top comedians.",
                "url": "https://streaming.example.com/videos/comedy-night",
                "duration_seconds": 7200,
                "genres": [genres[2]],
                "categories": [categories[3]],
            },
            {
                "title": "Space Warriors",
                "description": "An action-packed sci-fi adventure in outer space.",
                "url": "https://streaming.example.com/videos/space-warriors",
                "duration_seconds": 6000,
                "genres": [genres[0], genres[3]],
                "categories": [categories[3]],
            },
            {
                "title": "The Human Story",
                "description": "A short film about the human condition.",
                "url": "https://streaming.example.com/videos/human-story",
                "duration_seconds": 1800,
                "genres": [genres[1]],
                "categories": [categories[1]],
            },
        ]

        for vdata in videos_data:
            video = Video(
                id=uuid.uuid4(),
                title=vdata["title"],
                description=vdata["description"],
                url=vdata["url"],
                duration_seconds=vdata["duration_seconds"],
            )
            video.genres = vdata["genres"]
            video.categories = vdata["categories"]
            session.add(video)

        # Create admin user
        admin = User(
            id=uuid.uuid4(),
            name="Admin User",
            email="admin@streaming.com",
            password_hash=hash_password("admin123"),
            role=UserRole.ADMIN,
            plan_id=plans[2].id,
            is_active=True,
        )
        session.add(admin)

        await session.commit()
        print("Seed data created successfully!")
        print(f"  - {len(plans)} plans")
        print(f"  - {len(genres)} genres")
        print(f"  - {len(categories)} categories")
        print(f"  - {len(videos_data)} videos")
        print(f"  - 1 admin user (admin@streaming.com / admin123)")


if __name__ == "__main__":
    asyncio.run(seed())
