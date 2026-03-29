import sqlite3

def fix():
    try:
        conn = sqlite3.connect('/var/lib/aitbc/data/ait-mainnet/chain.db')
        cur = conn.cursor()
        
        cur.execute('PRAGMA table_info("block")')
        columns = [col[1] for col in cur.fetchall()]
        
        if 'metadata' in columns:
            print("Renaming metadata column to block_metadata...")
            cur.execute('ALTER TABLE "block" RENAME COLUMN metadata TO block_metadata')
            conn.commit()
        elif 'block_metadata' not in columns:
            print("Adding block_metadata column...")
            cur.execute('ALTER TABLE "block" ADD COLUMN block_metadata TEXT')
            conn.commit()
        else:
            print("block_metadata column already exists.")
            
        conn.close()
    except Exception as e:
        print(f"Error modifying database: {e}")

if __name__ == "__main__":
    fix()
