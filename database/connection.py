import aiomysql, logging

from pymysql.err import OperationalError

from core.config import config



class Database:
    _pool = None


    @classmethod
    async def init_pool(cls):
        logging.info("Connecting to MySQL...")
        cls._pool = await aiomysql.create_pool(
            host=config.DB_HOST,           # Database host from config
            port=config.DB_PORT,           # Database port from config
            user=config.DB_USER,           # Database user from config
            password=config.DB_PASSWORD,   # Database password from config
            db=config.DB_NAME,             # Database name from config
            autocommit=True,               # Automatically commit transactions
            minsize=1,                     # Minimum number of connections in the pool
            maxsize=10,                    # Maximum number of connections in the pool
        )
        logging.info("Database connection pool established.")


    @classmethod
    async def close_pool(cls):
        if cls._pool:
            cls._pool.close()
            await cls._pool.wait_closed()
            logging.info("Database connection pool closed.")


    @classmethod
    async def fetch(cls, query, args=None, retry: bool = True):
        try:
            async with cls._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(query, args or ())
                    return await cur.fetchall()
        except OperationalError:
            if retry:
                logging.warning(f"Retrying SQL query: {query}")
                await Database.fetch(query, args=args, retry=False)
            else:
                logging.error(f"SQL query failed: {query}")




    @classmethod
    async def fetchrow(cls, query, args=None):
        async with cls._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, args or ())
                return await cur.fetchone()


    @classmethod
    async def execute(cls, query, args=None):
        async with cls._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, args or ())
                return cur.lastrowid

