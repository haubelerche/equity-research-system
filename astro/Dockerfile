# Astro Runtime image for running the news-collection DAG (dags/collect_ticker_news_dag.py).
#
# IMPORTANT: build with the repo ROOT as the Docker context so backend/ + dags/ are included:
#     docker build -f astro/Dockerfile -t maer-airflow .
# Or, with the Astro CLI, keep this as the project Dockerfile and run `astro dev start`
# from a project whose context is the repo root (see astro/README.md).
#
# Pin to a current Astro Runtime tag (check https://quay.io/astronomer/astro-runtime tags).
# Astro Runtime 12.x ships Airflow 3.x; the DAG uses airflow.decorators imports that work on
# both Airflow 2 and 3 (deprecated on 3). Adjust the tag to match your target Airflow version.
FROM quay.io/astronomer/astro-runtime:12.1.1

USER root

# Project (backend) runtime dependencies. The DAG imports backend.news.runner etc.
COPY requirements.txt /tmp/app-requirements.txt
RUN pip install --no-cache-dir -r /tmp/app-requirements.txt

# Ship the project code so the DAG can import it.
COPY backend/ /usr/local/airflow/backend/
COPY dags/ /usr/local/airflow/dags/
ENV PYTHONPATH=/usr/local/airflow:${PYTHONPATH}

USER astro
