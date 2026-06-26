FROM python:3.11-slim

WORKDIR /project

COPY etl/requirements.txt ./etl/requirements.txt
RUN pip install --no-cache-dir -r etl/requirements.txt

COPY etl/__init__.py ./etl/__init__.py
COPY etl/recipe/__init__.py ./etl/recipe/__init__.py
COPY etl/recipe/load_to_postgres ./etl/recipe/load_to_postgres
COPY etl/food_guide ./etl/food_guide
COPY etl/load_to_neo4j ./etl/load_to_neo4j

ENV PYTHONPATH=/project
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "etl.recipe.load_to_postgres"]
