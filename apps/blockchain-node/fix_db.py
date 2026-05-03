from aitbc_chain.database import get_engine, init_db
from sqlalchemy import text

def fix():
    init_db()
    engine = get_engine()
    with engine.connect() as conn:
        try:
            conn.execute(text('ALTER TABLE "transaction" ADD COLUMN metadata TEXT'))
            print("Added metadata")
        except Exception as e:
            pass
        try:
            conn.execute(text('ALTER TABLE "transaction" ADD COLUMN value INTEGER DEFAULT 0'))
            print("Added value")
        except Exception as e:
            pass
        try:
            conn.execute(text('ALTER TABLE "transaction" ADD COLUMN fee INTEGER DEFAULT 0'))
            print("Added fee")
        except Exception as e:
            pass
        try:
            conn.execute(text('ALTER TABLE "transaction" ADD COLUMN nonce INTEGER DEFAULT 0'))
            print("Added nonce")
        except Exception as e:
            pass
        try:
            conn.execute(text('ALTER TABLE "transaction" ADD COLUMN status TEXT DEFAULT "pending"'))
            print("Added status")
        except Exception as e:
            pass
        try:
            conn.execute(text('ALTER TABLE "transaction" ADD COLUMN timestamp TEXT'))
            print("Added timestamp")
        except Exception as e:
            pass
        conn.commit()

if __name__ == "__main__":
    fix()
