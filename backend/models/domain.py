from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Vehicle(Base):
    __tablename__ = "vehicles"

    plate_normalized: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    plate_raw: Mapped[str] = mapped_column(String, nullable=False)
    nim: Mapped[str] = mapped_column(String, index=True, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="inactive", nullable=False)
    anpr_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Metadata for verification
    anpr_verified_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    anpr_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    ewallets: Mapped[List["EWallet"]] = relationship(
        "EWallet", back_populates="vehicle", cascade="all, delete-orphan"
    )
    history: Mapped[List["History"]] = relationship(
        "History", back_populates="vehicle", cascade="all, delete-orphan"
    )


class EWallet(Base):
    __tablename__ = "ewallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plate_normalized: Mapped[str] = mapped_column(
        String, ForeignKey("vehicles.plate_normalized", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    masked_account: Mapped[str] = mapped_column(String, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="ewallets")


class History(Base):
    __tablename__ = "history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plate_normalized: Mapped[str] = mapped_column(
        String, ForeignKey("vehicles.plate_normalized", ondelete="CASCADE"), nullable=False, index=True
    )
    gate_id: Mapped[str] = mapped_column(String, nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_secs: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fee: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)

    # Relationships
    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="history")
