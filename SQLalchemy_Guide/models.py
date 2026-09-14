from db import engine
import struct
from sqlalchemy import Integer, Text, LargeBinary
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    @property
    def embedding(self) -> list[float]:
        """Convenience property to decode the binary BLOB back into a list of floats."""
        # Counts how many 4-byte floats are in the binary data
        count = len(self.embedding_blob) // 4
        return list(struct.unpack(f"{count}f", self.embedding_blob))

    @embedding.setter
    def embedding(self, vector: list[float]):
        """Convenience property to encode a list of floats into a binary BLOB for SQLite."""
        self.embedding_blob = struct.pack(f"{len(vector)}f", *vector)


def create_table() -> None:
    Base.metadata.create_all(bind=engine)