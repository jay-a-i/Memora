from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DB_URL =  "sqlite:///sqlite_test.db"

engine = create_engine(DB_URL, echo=True)

Session = sessionmaker(bind=engine, expire_on_commit=False)