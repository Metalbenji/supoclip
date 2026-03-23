from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, String, DateTime, ForeignKey, CheckConstraint, ARRAY, Boolean, Float, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
import uuid

from .database import Base

def generate_uuid_string():
    """Generate a UUID as a string for compatibility with Prisma"""
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_string)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    emailVerified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updatedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), default=func.now())

    # Additional fields for backend compatibility
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    assembly_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    openai_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    google_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    anthropic_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    zai_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_font_weight: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("600"))
    default_highlight_color: Mapped[str] = mapped_column(String(7), nullable=False, server_default=text("'#FDE047'"))
    default_line_height: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1.4"))
    default_letter_spacing: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    default_text_transform: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'none'"))
    default_text_align: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'center'"))
    default_stroke_color: Mapped[str] = mapped_column(String(7), nullable=False, server_default=text("'#000000'"))
    default_stroke_width: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    default_stroke_blur: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.6"))
    default_shadow_color: Mapped[str] = mapped_column(String(7), nullable=False, server_default=text("'#000000'"))
    default_shadow_opacity: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.5"))
    default_shadow_blur: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    default_shadow_offset_x: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    default_shadow_offset_y: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    default_transitions_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    default_review_before_render_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    default_timeline_editor_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    default_transcription_provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'local'"),
    )
    default_whisper_chunking_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    default_whisper_chunk_duration_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1200"),
    )
    default_whisper_chunk_overlap_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("8"),
    )
    default_task_timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("21600"),
    )
    default_ai_provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'openai'"),
    )
    default_ollama_base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    default_ollama_profile: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_ollama_timeout_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    default_ollama_max_retries: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    default_ollama_retry_backoff_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    default_ai_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_zai_key_routing_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'auto'"),
    )

    # Relationships
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="user", cascade="all, delete-orphan")

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_string)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    generated_clips_ids: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String(36)), nullable=True)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"), nullable=False)
    review_before_render_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    timeline_editor_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # Font customization fields
    font_family: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, server_default=text("'TikTokSans-Regular'"))
    font_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, server_default=text("'24'"))
    font_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True, server_default=text("'#FFFFFF'"))  # Hex color code
    subtitle_style: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    transitions_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    transcription_provider: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'local'"))
    ai_provider: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'openai'"))
    ai_focus_tags: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tasks")
    source: Mapped[Optional["Source"]] = relationship("Source", back_populates="tasks")
    generated_clips: Mapped[List["GeneratedClip"]] = relationship("GeneratedClip", back_populates="task", cascade="all, delete-orphan")
    draft_clips: Mapped[List["TaskClipDraft"]] = relationship("TaskClipDraft", back_populates="task", cascade="all, delete-orphan")

class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_string)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Add check constraint for type enum
    __table_args__ = (
        CheckConstraint("type IN ('youtube', 'video_url')", name="check_source_type"),
    )

    # Relationships - Source can have multiple tasks
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="source")

    def decide_source_type(self, source_url: str) -> str:
      """Decide which type of source this is."""
      if "youtube" in source_url:
        return "youtube"
      else:
        return "video_url"

class GeneratedClip(Base):
    __tablename__ = "generated_clips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_string)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    start_time: Mapped[str] = mapped_column(String(20), nullable=False)  # MM:SS format
    end_time: Mapped[str] = mapped_column(String(20), nullable=False)    # MM:SS format
    duration: Mapped[float] = mapped_column(Float, nullable=False)       # Duration in seconds
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # Transcript text for this clip
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # AI reasoning for selection
    clip_order: Mapped[int] = mapped_column(Integer, nullable=False)     # Order within the task
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="generated_clips")


class TaskClipDraft(Base):
    __tablename__ = "task_clip_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_string)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    clip_order: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[str] = mapped_column(String(20), nullable=False)
    end_time: Mapped[str] = mapped_column(String(20), nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)
    original_start_time: Mapped[str] = mapped_column(String(20), nullable=False)
    original_end_time: Mapped[str] = mapped_column(String(20), nullable=False)
    original_duration: Mapped[float] = mapped_column(Float, nullable=False)
    original_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    review_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    feedback_score_adjustment: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    feedback_signals_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    edited_word_timings_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    task: Mapped["Task"] = relationship("Task", back_populates="draft_clips")
