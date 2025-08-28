
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor
import os
import logging

logger = logging.getLogger(__name__)

# Initialize connection pool
# Min connections: 1, Max connections: 10
# Adjust these values based on expected load
conn_pool = None

def init_db_pool():
    global conn_pool
    if conn_pool is None:
        try:
            conn_pool = SimpleConnectionPool(
                minconn=1, 
                maxconn=10, 
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5432"),
                database=os.getenv("DB_NAME", "movecrm"),
                user=os.getenv("DB_USER", "movecrm"),
                password=os.getenv("DB_PASSWORD", "movecrm_password"),
                connect_timeout=10
            )
            logger.info("Database connection pool initialized.")
        except psycopg2.Error as e:
            logger.critical(f"Failed to initialize database connection pool: {e}")
            raise

class DatabaseManager:
    """Manages database connections from a connection pool."""

    def __init__(self):
        if conn_pool is None:
            init_db_pool()

    def __enter__(self):
        self.conn = conn_pool.getconn()
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.conn.rollback()
            logger.error(f"Database transaction rolled back due to exception: {exc_val}")
        else:
            self.conn.commit()
        self.cursor.close()
        conn_pool.putconn(self.conn)

def get_db_connection():
    """Legacy function for direct connection (to be replaced by DatabaseManager)"""
    try:
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "movecrm"),
            user=os.getenv("DB_USER", "movecrm"),
            password=os.getenv("DB_PASSWORD", "movecrm_password"),
            connect_timeout=10
        )
    except psycopg2.Error as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise

# Call init_db_pool when the module is imported
init_db_pool()


