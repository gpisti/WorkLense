FROM apache/airflow:2.10.5-python3.10

COPY requirements-etl.txt /tmp/requirements-etl.txt
RUN pip install --no-cache-dir --timeout 300 -r /tmp/requirements-etl.txt

# -----------------------------------------------------------------------------
# Gál István – szakdolgozat. A megvalósítás során mesterséges intelligencia (AI) eszközöket használtam.
