"""Maps API video UUIDs to integer content_ids used by VodRec vocab."""

from __future__ import annotations

from uuid import UUID


class ContentIdMapper:
    def __init__(self) -> None:
        self._video_to_content: dict[UUID, int] = {}
        self._content_to_video: dict[int, UUID] = {}

    def clear(self) -> None:
        self._video_to_content.clear()
        self._content_to_video.clear()

    def build(self, video_ids: list[UUID]) -> None:
        """Assign content_ids 1..N in stable sorted UUID order (platform Postgres)."""
        self.clear()
        for index, video_id in enumerate(sorted(video_ids, key=str), start=1):
            self._video_to_content[video_id] = index
            self._content_to_video[index] = video_id

    def build_legacy_int_ids(self, content_ids: list[int]) -> None:
        """Map integer content ids 1:1 to deterministic UUIDs (SQLite tests)."""
        self.clear()
        for content_id in content_ids:
            video_id = UUID(int=int(content_id))
            self._video_to_content[video_id] = int(content_id)
            self._content_to_video[int(content_id)] = video_id

    def video_to_content(self, video_id: UUID) -> int | None:
        return self._video_to_content.get(video_id)

    def content_to_video(self, content_id: int) -> UUID | None:
        return self._content_to_video.get(int(content_id))

    def videos_to_contents(self, video_ids: list[UUID]) -> list[int]:
        out: list[int] = []
        for video_id in video_ids:
            content_id = self.video_to_content(video_id)
            if content_id is not None:
                out.append(content_id)
        return out


_mapper = ContentIdMapper()


def get_mapper() -> ContentIdMapper:
    return _mapper
