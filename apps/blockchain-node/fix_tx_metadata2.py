import sqlite3

def fix_db():
    print("Fixing transaction table on aitbc node...")
    
    conn = sqlite3.connect('/var/lib/aitbc/data/ait-mainnet/chain.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('ALTER TABLE "transaction" ADD COLUMN nonce INTEGER DEFAULT 0;')
        print("Added nonce column")
    except sqlite3.OperationalError as e:
        print(f"Error adding nonce: {e}")
        
    try:
        cursor.execute('ALTER TABLE "transaction" ADD COLUMN value INTEGER DEFAULT 0;')
        print("Added value column")
    except sqlite3.OperationalError as e:
        print(f"Error adding value: {e}")
        
    try:
        cursor.execute('ALTER TABLE "transaction" ADD COLUMN fee INTEGER DEFAULT 0;')
        print("Added fee column")
    except sqlite3.OperationalError as e:
        print(f"Error adding fee: {e}")
        
    try:
        cursor.execute('ALTER TABLE "transaction" ADD COLUMN status TEXT DEFAULT "pending";')
        print("Added status column")
    except sqlite3.OperationalError as e:
        print(f"Error adding status: {e}")
        
    try:
        cursor.execute('ALTER TABLE "transaction" ADD COLUMN tx_metadata TEXT;')
        print("Added tx_metadata column")
    except sqlite3.OperationalError as e:
        print(f"Error adding tx_metadata: {e}")
        
    try:
        cursor.execute('ALTER TABLE "transaction" ADD COLUMN timestamp TEXT;')
        print("Added timestamp column")
    except sqlite3.OperationalError as e:
        print(f"Error adding timestamp: {e}")
        
    conn.commit()
    conn.close()
    print("Done fixing transaction table.")

if __name__ == '__main__':
    fix_db()
