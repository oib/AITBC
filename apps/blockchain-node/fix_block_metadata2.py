import sqlite3

def fix():
    try:
        conn = sqlite3.connect('/var/lib/aitbc/data/chain.db')
        cur = conn.cursor()
        
        cur.execute('PRAGMA table_info("block")')
        columns = [col[1] for col in cur.fetchall()]
        
        if 'metadata' in columns:
            print("Renaming metadata column to block_metadata in default db...")
            cur.execute('ALTER TABLE "block" RENAME COLUMN metadata TO block_metadata')
            conn.commit()
        elif 'block_metadata' not in columns:
            print("Adding block_metadata column to default db...")
            cur.execute('ALTER TABLE "block" ADD COLUMN block_metadata TEXT')
            conn.commit()
        else:
            print("block_metadata column already exists in default db.")
            
        cur.execute('PRAGMA table_info("transaction")')
        columns = [col[1] for col in cur.fetchall()]
        
        if 'metadata' in columns:
            print("Renaming metadata column to tx_metadata in default db...")
            cur.execute('ALTER TABLE "transaction" RENAME COLUMN metadata TO tx_metadata')
            conn.commit()
        elif 'tx_metadata' not in columns:
            print("Adding tx_metadata column to default db...")
            cur.execute('ALTER TABLE "transaction" ADD COLUMN tx_metadata TEXT')
            conn.commit()
            
        conn.close()
    except Exception as e:
        print(f"Error modifying database: {e}")

if __name__ == "__main__":
    fix()
