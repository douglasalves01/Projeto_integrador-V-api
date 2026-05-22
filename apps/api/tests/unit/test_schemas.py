"""Unit tests for Pydantic schema validation."""
import uuid

import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate
from app.schemas.video import VideoCreate, VideoUpdate
from app.schemas.genre import GenreCreate
from app.schemas.category import CategoryCreate
from app.schemas.plan import PlanCreate
from app.schemas.watch_session import WatchSessionUpdate


class TestUserCreateSchema:
    def test_valid_user(self):
        user = UserCreate(
            name="Test User",
            email="test@example.com",
            password="securepass123",
            plan_id=uuid.uuid4(),
        )
        assert user.name == "Test User"

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            UserCreate(
                name="Test", email="not-email", password="securepass123", plan_id=uuid.uuid4()
            )

    def test_password_too_short(self):
        with pytest.raises(ValidationError):
            UserCreate(
                name="Test", email="test@example.com", password="short", plan_id=uuid.uuid4()
            )

    def test_password_too_long(self):
        with pytest.raises(ValidationError):
            UserCreate(
                name="Test", email="test@example.com", password="a" * 129, plan_id=uuid.uuid4()
            )

    def test_name_empty(self):
        with pytest.raises(ValidationError):
            UserCreate(
                name="", email="test@example.com", password="securepass123", plan_id=uuid.uuid4()
            )

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            UserCreate(
                name="A" * 101, email="test@example.com", password="securepass123", plan_id=uuid.uuid4()
            )


class TestVideoCreateSchema:
    def test_valid_video(self):
        video = VideoCreate(
            title="Test Video",
            description="A description",
            url="https://example.com/video.mp4",
            duration_seconds=3600,
            genre_ids=[uuid.uuid4()],
            category_ids=[uuid.uuid4()],
        )
        assert video.title == "Test Video"

    def test_title_too_long(self):
        with pytest.raises(ValidationError):
            VideoCreate(
                title="T" * 201,
                url="https://example.com/video.mp4",
                duration_seconds=3600,
                genre_ids=[uuid.uuid4()],
                category_ids=[uuid.uuid4()],
            )

    def test_description_too_long(self):
        with pytest.raises(ValidationError):
            VideoCreate(
                title="Test",
                description="D" * 2001,
                url="https://example.com/video.mp4",
                duration_seconds=3600,
                genre_ids=[uuid.uuid4()],
                category_ids=[uuid.uuid4()],
            )

    def test_url_too_long(self):
        with pytest.raises(ValidationError):
            VideoCreate(
                title="Test",
                url="https://example.com/" + "a" * 500,
                duration_seconds=3600,
                genre_ids=[uuid.uuid4()],
                category_ids=[uuid.uuid4()],
            )

    def test_duration_zero(self):
        with pytest.raises(ValidationError):
            VideoCreate(
                title="Test",
                url="https://example.com/video.mp4",
                duration_seconds=0,
                genre_ids=[uuid.uuid4()],
                category_ids=[uuid.uuid4()],
            )

    def test_duration_negative(self):
        with pytest.raises(ValidationError):
            VideoCreate(
                title="Test",
                url="https://example.com/video.mp4",
                duration_seconds=-1,
                genre_ids=[uuid.uuid4()],
                category_ids=[uuid.uuid4()],
            )

    def test_duration_exceeds_max(self):
        with pytest.raises(ValidationError):
            VideoCreate(
                title="Test",
                url="https://example.com/video.mp4",
                duration_seconds=86401,
                genre_ids=[uuid.uuid4()],
                category_ids=[uuid.uuid4()],
            )

    def test_empty_genre_ids(self):
        with pytest.raises(ValidationError):
            VideoCreate(
                title="Test",
                url="https://example.com/video.mp4",
                duration_seconds=3600,
                genre_ids=[],
                category_ids=[uuid.uuid4()],
            )

    def test_empty_category_ids(self):
        with pytest.raises(ValidationError):
            VideoCreate(
                title="Test",
                url="https://example.com/video.mp4",
                duration_seconds=3600,
                genre_ids=[uuid.uuid4()],
                category_ids=[],
            )


class TestGenreCreateSchema:
    def test_valid_genre(self):
        genre = GenreCreate(name="Action")
        assert genre.name == "Action"

    def test_empty_name(self):
        with pytest.raises(ValidationError):
            GenreCreate(name="")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            GenreCreate(name="A" * 101)


class TestCategoryCreateSchema:
    def test_valid_category(self):
        cat = CategoryCreate(name="Documentary")
        assert cat.name == "Documentary"

    def test_empty_name(self):
        with pytest.raises(ValidationError):
            CategoryCreate(name="")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            CategoryCreate(name="C" * 101)


class TestPlanCreateSchema:
    def test_valid_plan(self):
        from decimal import Decimal

        plan = PlanCreate(name="Premium", price=Decimal("29.90"))
        assert plan.name == "Premium"
        assert plan.price == Decimal("29.90")

    def test_empty_name(self):
        with pytest.raises(ValidationError):
            PlanCreate(name="")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            PlanCreate(name="P" * 101)


class TestWatchSessionUpdateSchema:
    def test_valid_update(self):
        update = WatchSessionUpdate(watch_time_seconds=1800)
        assert update.watch_time_seconds == 1800

    def test_negative_watch_time(self):
        with pytest.raises(ValidationError):
            WatchSessionUpdate(watch_time_seconds=-1)

    def test_zero_watch_time(self):
        update = WatchSessionUpdate(watch_time_seconds=0)
        assert update.watch_time_seconds == 0
