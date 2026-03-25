import aiosqlite

DB_PATH = "bot_data.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                prompt TEXT
            )
        ''')
        await db.commit()

async def set_prompt(user_id: int, prompt: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO users (user_id, prompt) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET prompt=excluded.prompt
        ''', (user_id, prompt))
        await db.commit()

async def get_prompt(user_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT prompt FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def clear_prompt(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        await db.commit()
