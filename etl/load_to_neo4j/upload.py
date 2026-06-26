import os
import pandas as pd
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://neo4j:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

CSV_PATH = r"c:/dev/project/SKN27-FINAL-1Team/storage/processed/food_guide/food_guide_v1.csv"

def load_csv(path):
    return pd.read_csv(path, encoding='utf-8')

def upload_to_neo4j(df):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        for _, row in df.iterrows():
            session.run(
                """
                MERGE (i:Ingredient {name: $name})
                MERGE (s:Storage {method: $storage})
                MERGE (i)-[:HAS_STORAGE]->(s)
                """,
                name=row['원재료명'],
                storage=row['보관']
            )
    driver.close()

if __name__ == '__main__':
    df = load_csv(CSV_PATH)
    upload_to_neo4j(df)
    print('✅ Neo4j upload completed')
