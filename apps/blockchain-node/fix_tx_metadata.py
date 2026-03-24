import sqlite3

def fix():
    try:
        conn = sqlite3.connect('/opt/aitbc/data/ait-mainnet/chain.db')
        cur = conn.cursor()
        
        cur.execute('PRAGMA table_info("transaction")')
        columns = [col[1] for col in cur.fetchall()]
        
        if 'metadata' in columns:
            print("Renaming metadata column to tx_metadata...")
            cur.execute('ALTER TABLE "transaction" RENAME COLUMN metadata TO tx_metadata')
            conn.commit()
        elif 'tx_metadata' not in columns:
            print("Adding tx_metadata column...")
            cur.execute('ALTER TABLE "transaction" ADD COLUMN tx_metadata TEXT')
            conn.commit()
        else:
            print("tx_metadata column already exists.")
            
        conn.close()
    except Exception as e:
        print(f"Error modifying database: {e}")

if __name__ == "__main__":
    fix()
